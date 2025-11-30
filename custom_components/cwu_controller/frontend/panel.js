/**
 * CWU Controller Panel JavaScript
 * A beautiful, functional dashboard for managing CWU heat pump controller
 */

// Configuration
const CONFIG = {
    updateInterval: 5000, // 5 seconds
    chartUpdateInterval: 60000, // 1 minute
    maxRetries: 3,
    retryDelay: 2000,
    chartRange: '6h', // default chart range
};

// Entity IDs - these will be fetched from the state sensor attributes
let ENTITIES = {
    state: 'sensor.cwu_controller_state',
    cwuUrgency: 'sensor.cwu_controller_cwu_urgency',
    floorUrgency: 'sensor.cwu_controller_floor_urgency',
    avgPower: 'sensor.cwu_controller_average_power',
    heatingTime: 'sensor.cwu_controller_cwu_heating_time',
    enabled: 'switch.cwu_controller_enabled',
    cwuHeating: 'binary_sensor.cwu_controller_cwu_heating',
    floorHeating: 'binary_sensor.cwu_controller_floor_heating',
    fakeHeating: 'binary_sensor.cwu_controller_fake_heating',
    manualOverride: 'binary_sensor.cwu_controller_manual_override',
};

// External sensor entity IDs (from config)
let EXTERNAL_ENTITIES = {
    cwuTemp: 'sensor.temperatura_c_w_u',
    salonTemp: 'sensor.temperatura_govee_salon',
    bedroomTemp: 'sensor.temperatura_govee_sypialnia',
    kidsTemp: 'sensor.temperatura_govee_dzieciecy',
    power: 'sensor.ogrzewanie_total_system_power',
    waterHeater: 'water_heater.pompa_ciepla_io_13873843_2',
    climate: 'climate.pompa_ciepla_dom',
};

// State icons mapping
const STATE_ICONS = {
    'idle': 'mdi-sleep',
    'heating_cwu': 'mdi-water-boiler',
    'heating_floor': 'mdi-heating-coil',
    'pause': 'mdi-pause-circle',
    'emergency_cwu': 'mdi-water-boiler-alert',
    'emergency_floor': 'mdi-home-alert',
    'fake_heating_detected': 'mdi-alert-circle',
};

const STATE_CLASSES = {
    'heating_cwu': 'state-heating-cwu',
    'heating_floor': 'state-heating-floor',
    'emergency_cwu': 'state-emergency',
    'emergency_floor': 'state-emergency',
    'fake_heating_detected': 'state-emergency',
    'pause': 'state-pause',
};

const STATE_DESCRIPTIONS = {
    'idle': 'System is monitoring, ready to act when needed',
    'heating_cwu': 'Actively heating domestic hot water tank',
    'heating_floor': 'Actively heating floor (underfloor heating)',
    'pause': 'Mandatory 10-minute pause (3h cycle limit reached)',
    'emergency_cwu': 'Emergency! CWU temperature critically low (<35°C)',
    'emergency_floor': 'Emergency! Room temperature critically low (<19°C)',
    'fake_heating_detected': 'Warning: Broken heater situation detected - power <10W',
};

const URGENCY_COLORS = ['#68d391', '#8BC34A', '#FF9800', '#FF5722', '#F44336'];
const URGENCY_LEVELS = ['None', 'Low', 'Medium', 'High', 'Critical'];

// Data storage
let currentData = {};
let updateTimer = null;
let chartUpdateTimer = null;
let tempChart = null;
let powerChart = null;
let stateStartTime = null;

/**
 * Initialize the panel
 */
async function init() {
    console.log('CWU Controller Panel initializing...');

    // Set up event listeners
    document.getElementById('controller-toggle').addEventListener('change', toggleController);

    // Initialize charts
    initCharts();

    // Start data fetching
    await refreshData();

    // Fetch chart history
    await updateChartData();

    // Set up auto-refresh
    updateTimer = setInterval(refreshData, CONFIG.updateInterval);
    chartUpdateTimer = setInterval(updateChartData, CONFIG.chartUpdateInterval);

    // Update last update time
    updateLastUpdateTime();
    setInterval(updateLastUpdateTime, 1000);

    console.log('CWU Controller Panel initialized');
}

/**
 * Get authentication token from Home Assistant
 */
function getToken() {
    // Try to get token from parent window (Home Assistant iframe)
    try {
        if (window.parent && window.parent.hassConnection) {
            return window.parent.hassConnection.options.auth.accessToken;
        }
    } catch (e) {}

    // Try legacy approach
    try {
        if (window.parent && window.parent.document) {
            const haMain = window.parent.document.querySelector('home-assistant');
            if (haMain && haMain.hass) {
                return haMain.hass.auth.data.access_token;
            }
        }
    } catch (e) {}

    // Fallback: try to extract from URL or use stored token
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('token') || localStorage.getItem('ha_token') || '';
}

/**
 * Fetch data from Home Assistant API
 */
async function fetchState(entityId) {
    try {
        const response = await fetch(`/api/states/${entityId}`, {
            headers: {
                'Authorization': `Bearer ${getToken()}`,
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`Failed to fetch ${entityId}:`, error);
        return null;
    }
}

/**
 * Fetch history data for charts
 */
async function fetchHistory(entityId, hoursBack = 6) {
    try {
        const endTime = new Date();
        const startTime = new Date(endTime.getTime() - hoursBack * 60 * 60 * 1000);

        const url = `/api/history/period/${startTime.toISOString()}?filter_entity_id=${entityId}&end_time=${endTime.toISOString()}&minimal_response&no_attributes`;

        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${getToken()}`,
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        return data[0] || [];
    } catch (error) {
        console.error(`Failed to fetch history for ${entityId}:`, error);
        return [];
    }
}

/**
 * Call a Home Assistant service
 */
async function callService(domain, service, data = {}) {
    try {
        const response = await fetch(`/api/services/${domain}/${service}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${getToken()}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        showNotification('Action executed successfully', 'success');
        setTimeout(refreshData, 1000);
        return true;
    } catch (error) {
        console.error(`Failed to call ${domain}.${service}:`, error);
        showNotification('Failed to execute action', 'error');
        return false;
    }
}

/**
 * Refresh all data
 */
async function refreshData() {
    try {
        // Fetch main state sensor (has most data in attributes)
        const stateData = await fetchState(ENTITIES.state);
        if (stateData) {
            // Track state changes for duration
            if (currentData.state !== stateData.state) {
                stateStartTime = new Date();
            }
            currentData.state = stateData.state;
            currentData.attributes = stateData.attributes || {};
        }

        // Fetch other sensors in parallel
        const [urgencyCwu, urgencyFloor, avgPower, heatingTime, enabled, fakeHeating, override, cwuHeating, floorHeating] = await Promise.all([
            fetchState(ENTITIES.cwuUrgency),
            fetchState(ENTITIES.floorUrgency),
            fetchState(ENTITIES.avgPower),
            fetchState(ENTITIES.heatingTime),
            fetchState(ENTITIES.enabled),
            fetchState(ENTITIES.fakeHeating),
            fetchState(ENTITIES.manualOverride),
            fetchState(ENTITIES.cwuHeating),
            fetchState(ENTITIES.floorHeating),
        ]);

        if (urgencyCwu) currentData.cwuUrgency = parseFloat(urgencyCwu.state) || 0;
        if (urgencyFloor) currentData.floorUrgency = parseFloat(urgencyFloor.state) || 0;
        if (avgPower) currentData.avgPower = parseFloat(avgPower.state) || 0;
        if (heatingTime) currentData.heatingTime = parseFloat(heatingTime.state) || 0;
        if (enabled) currentData.enabled = enabled.state === 'on';
        if (fakeHeating) currentData.fakeHeating = fakeHeating.state === 'on';
        if (override) currentData.manualOverride = override.state === 'on';
        if (cwuHeating) currentData.cwuHeatingActive = cwuHeating.state === 'on';
        if (floorHeating) currentData.floorHeatingActive = floorHeating.state === 'on';

        // Fetch external sensor data
        const [cwuTemp, salonTemp, bedroomTemp, kidsTemp, power, waterHeater, climate] = await Promise.all([
            fetchState(EXTERNAL_ENTITIES.cwuTemp),
            fetchState(EXTERNAL_ENTITIES.salonTemp),
            fetchState(EXTERNAL_ENTITIES.bedroomTemp),
            fetchState(EXTERNAL_ENTITIES.kidsTemp),
            fetchState(EXTERNAL_ENTITIES.power),
            fetchState(EXTERNAL_ENTITIES.waterHeater),
            fetchState(EXTERNAL_ENTITIES.climate),
        ]);

        if (cwuTemp) currentData.cwuTemp = parseFloat(cwuTemp.state);
        if (salonTemp) currentData.salonTemp = parseFloat(salonTemp.state);
        if (bedroomTemp) currentData.bedroomTemp = parseFloat(bedroomTemp.state);
        if (kidsTemp) currentData.kidsTemp = parseFloat(kidsTemp.state);
        if (power) currentData.power = parseFloat(power.state) || 0;
        if (waterHeater) currentData.waterHeaterState = waterHeater.state;
        if (climate) currentData.climateState = climate.state;

        // Update connection status
        document.getElementById('connection-state').textContent = 'Connected';
        document.getElementById('connection-state').style.color = '#68d391';

        // Update UI
        updateUI();
    } catch (error) {
        console.error('Failed to refresh data:', error);
        document.getElementById('connection-state').textContent = 'Error';
        document.getElementById('connection-state').style.color = '#fc8181';
    }
}

/**
 * Update UI with current data
 */
function updateUI() {
    const attrs = currentData.attributes || {};

    // Update controller status
    updateControllerStatus();

    // Update state display
    updateStateDisplay();

    // Update heating indicators
    updateHeatingIndicators();

    // Update temperatures
    updateTemperature('temp-cwu', currentData.cwuTemp || attrs.cwu_temp, 45, 35);
    updateTemperature('temp-salon', currentData.salonTemp || attrs.salon_temp, 22, 19);
    updateTemperature('temp-bedroom', currentData.bedroomTemp || attrs.bedroom_temp, 20, 19);
    updateTemperature('temp-kids', currentData.kidsTemp || attrs.kids_temp, 20, 19);

    // Update temperature status badge
    updateTempStatus();

    // Update urgency gauges
    updateUrgencyGauge('cwu', currentData.cwuUrgency || 0);
    updateUrgencyGauge('floor', currentData.floorUrgency || 0);

    // Update power display
    updatePowerDisplay(currentData.power || attrs.power, currentData.avgPower);

    // Update cycle timer
    updateCycleTimer(currentData.heatingTime || 0);

    // Update heat pump status
    updateHeatPumpStatus();

    // Update fake heating alert
    updateFakeHeatingAlert();

    // Update override alert
    updateOverrideAlert();

    // Update history
    updateActionHistory(attrs.action_history || []);
    updateStateHistory(attrs.state_history || []);
}

/**
 * Update controller status badge
 */
function updateControllerStatus() {
    const statusEl = document.getElementById('controller-status');
    const toggleEl = document.getElementById('controller-toggle');
    const isEnabled = currentData.enabled;

    statusEl.className = `status-badge ${isEnabled ? 'enabled' : 'disabled'}`;
    statusEl.querySelector('.status-dot').className = `status-dot ${isEnabled ? 'active' : 'inactive'}`;
    statusEl.querySelector('.status-text').textContent = isEnabled ? 'Active' : 'Disabled';

    toggleEl.checked = isEnabled;
}

/**
 * Update heating indicators
 */
function updateHeatingIndicators() {
    const cwuIndicator = document.getElementById('cwu-indicator');
    const floorIndicator = document.getElementById('floor-indicator');

    cwuIndicator.className = `indicator ${currentData.cwuHeatingActive ? 'active' : ''}`;
    floorIndicator.className = `indicator ${currentData.floorHeatingActive ? 'active' : ''}`;
}

/**
 * Update state display
 */
function updateStateDisplay() {
    const displayEl = document.getElementById('state-display');
    const iconEl = displayEl.querySelector('.state-icon');
    const nameEl = document.getElementById('state-name');
    const descEl = document.getElementById('state-description');
    const timeEl = document.getElementById('state-time');
    const durationEl = document.getElementById('state-duration');

    const state = currentData.state || 'unknown';
    const stateName = state.replace(/_/g, ' ');

    // Update icon
    const iconClass = STATE_ICONS[state] || 'mdi-help-circle';
    iconEl.className = `state-icon mdi ${iconClass}`;

    // Update name
    nameEl.textContent = stateName.charAt(0).toUpperCase() + stateName.slice(1);

    // Update description
    descEl.textContent = STATE_DESCRIPTIONS[state] || 'Unknown state';

    // Update time
    const now = new Date();
    timeEl.innerHTML = `<span class="mdi mdi-clock-outline"></span> ${now.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}`;

    // Update duration
    if (stateStartTime) {
        const duration = Math.floor((now - stateStartTime) / 1000 / 60);
        durationEl.innerHTML = `<span class="mdi mdi-timer-outline"></span> ${duration} min`;
    }

    // Update class for styling
    displayEl.className = 'state-display';
    if (STATE_CLASSES[state]) {
        displayEl.classList.add(STATE_CLASSES[state]);
    }
}

/**
 * Update temperature display
 */
function updateTemperature(elementId, value, targetTemp, minTemp) {
    const el = document.getElementById(elementId);
    const valueEl = el.querySelector('.value');
    const barFill = el.querySelector('.temp-bar-fill');

    if (value === null || value === undefined || isNaN(value)) {
        valueEl.innerHTML = '--<span class="unit">°C</span>';
        el.className = 'temp-item';
        if (barFill) barFill.style.width = '0%';
        return;
    }

    const temp = parseFloat(value).toFixed(1);
    valueEl.innerHTML = `${temp}<span class="unit">°C</span>`;

    // Calculate bar width (0-100% based on range)
    const range = targetTemp - minTemp + 10; // add some margin
    const progress = Math.min(100, Math.max(0, ((value - minTemp + 5) / range) * 100));
    if (barFill) barFill.style.width = `${progress}%`;

    // Determine status class based on element type
    let statusClass = 'good';

    if (elementId === 'temp-cwu') {
        if (value < 35) statusClass = 'critical';
        else if (value < 40) statusClass = 'warning';
    } else {
        if (value < 19) statusClass = 'critical';
        else if (value < 21) statusClass = 'warning';
    }

    el.className = `temp-item ${statusClass}`;

    // Update bar color
    if (barFill) {
        if (statusClass === 'critical') barFill.style.background = 'linear-gradient(90deg, #fc8181, #f56565)';
        else if (statusClass === 'warning') barFill.style.background = 'linear-gradient(90deg, #ed8936, #dd6b20)';
        else barFill.style.background = 'linear-gradient(90deg, #68d391, #48bb78)';
    }
}

/**
 * Update temperature status badge
 */
function updateTempStatus() {
    const badge = document.getElementById('temp-status');
    const temps = [
        { val: currentData.cwuTemp, min: 35, warn: 40 },
        { val: currentData.salonTemp, min: 19, warn: 21 },
        { val: currentData.bedroomTemp, min: 19, warn: 21 },
        { val: currentData.kidsTemp, min: 19, warn: 21 },
    ];

    let hasCritical = false;
    let hasWarning = false;

    temps.forEach(t => {
        if (t.val !== undefined && !isNaN(t.val)) {
            if (t.val < t.min) hasCritical = true;
            else if (t.val < t.warn) hasWarning = true;
        }
    });

    if (hasCritical) {
        badge.textContent = 'CRITICAL';
        badge.className = 'badge badge-danger';
    } else if (hasWarning) {
        badge.textContent = 'Warning';
        badge.className = 'badge badge-warning';
    } else {
        badge.textContent = 'OK';
        badge.className = 'badge badge-success';
    }
}

/**
 * Update urgency gauge
 */
function updateUrgencyGauge(type, value) {
    const circle = document.getElementById(`${type}-urgency-circle`);
    const valueEl = document.getElementById(`${type}-urgency-value`);
    const levelEl = document.getElementById(`${type}-urgency-level`);

    // Update value text
    valueEl.textContent = value.toFixed(1);

    // Calculate stroke offset (377 is circumference for r=60)
    const percentage = Math.min(value / 4, 1);
    const offset = 377 - (377 * percentage);
    circle.style.strokeDashoffset = offset;

    // Update color
    const colorIndex = Math.min(Math.floor(value), 4);
    circle.style.stroke = URGENCY_COLORS[colorIndex];
    valueEl.style.color = URGENCY_COLORS[colorIndex];

    // Update level text
    levelEl.textContent = URGENCY_LEVELS[colorIndex];
    levelEl.style.color = URGENCY_COLORS[colorIndex];
}

/**
 * Update power display
 */
function updatePowerDisplay(power, avgPower) {
    const valueEl = document.getElementById('power-value');
    const barEl = document.getElementById('power-bar');
    const avgEl = document.getElementById('power-avg');
    const statusEl = document.getElementById('power-status');
    const indicatorEl = document.getElementById('power-indicator');
    const statusTextEl = document.getElementById('power-status-text');
    const modeEl = document.getElementById('power-mode');

    const powerVal = parseFloat(power) || 0;
    valueEl.textContent = Math.round(powerVal);
    avgEl.textContent = Math.round(avgPower || 0);

    // Calculate bar width and color
    const maxPower = 1500;
    const percentage = Math.min((powerVal / maxPower) * 100, 100);
    barEl.style.width = `${percentage}%`;

    // Determine color class and status
    let colorClass = 'low';
    let statusText = 'Idle';
    let badgeClass = 'badge';

    if (powerVal < 10) {
        colorClass = 'idle';
        statusText = 'Standby';
        badgeClass = 'badge badge-secondary';
    } else if (powerVal < 100) {
        colorClass = 'low';
        statusText = 'Idle';
        badgeClass = 'badge badge-info';
    } else if (powerVal < 500) {
        colorClass = 'medium';
        statusText = 'Transitioning';
        badgeClass = 'badge badge-warning';
    } else if (powerVal < 1000) {
        colorClass = 'high';
        statusText = 'Heating';
        badgeClass = 'badge badge-success';
    } else {
        colorClass = 'max';
        statusText = 'Full Power';
        badgeClass = 'badge badge-danger';
    }

    barEl.className = `power-bar-fill ${colorClass}`;
    statusEl.textContent = `${Math.round(powerVal)}W`;
    statusEl.className = badgeClass;
    indicatorEl.className = `power-indicator ${colorClass}`;
    statusTextEl.textContent = statusText;

    // Determine mode
    if (currentData.cwuHeatingActive) {
        modeEl.textContent = 'CWU Mode';
    } else if (currentData.floorHeatingActive) {
        modeEl.textContent = 'Floor Mode';
    } else {
        modeEl.textContent = 'Standby';
    }
}

/**
 * Update cycle timer
 */
function updateCycleTimer(minutes) {
    const timeEl = document.getElementById('cycle-time');
    const progressEl = document.getElementById('cycle-progress');
    const remainingEl = document.getElementById('cycle-remaining');
    const percentEl = document.getElementById('cycle-percent');
    const statusEl = document.getElementById('cycle-status');
    const warningEl = document.getElementById('cycle-warning');

    const maxMinutes = 170; // Just under 3 hours
    const mins = Math.round(minutes);
    const remaining = Math.max(0, maxMinutes - mins);

    timeEl.textContent = mins;
    remainingEl.textContent = remaining;

    // Calculate progress (502 is circumference for r=80)
    const percentage = Math.min(mins / maxMinutes, 1);
    const offset = 502 - (502 * percentage);
    progressEl.style.strokeDashoffset = offset;
    percentEl.textContent = Math.round(percentage * 100);

    // Update status badge
    if (mins === 0) {
        statusEl.textContent = 'Idle';
        statusEl.className = 'badge badge-secondary';
    } else if (percentage > 0.9) {
        statusEl.textContent = 'Almost Full';
        statusEl.className = 'badge badge-danger';
    } else if (percentage > 0.7) {
        statusEl.textContent = 'Active';
        statusEl.className = 'badge badge-warning';
    } else {
        statusEl.textContent = 'Active';
        statusEl.className = 'badge badge-info';
    }

    // Show warning if approaching limit
    warningEl.style.display = percentage > 0.9 ? 'flex' : 'none';

    // Change color based on progress
    if (percentage > 0.9) {
        progressEl.style.stroke = '#fc8181';
    } else if (percentage > 0.7) {
        progressEl.style.stroke = '#ed8936';
    } else {
        progressEl.style.stroke = 'url(#timer-gradient)';
    }
}

/**
 * Update heat pump status
 */
function updateHeatPumpStatus() {
    const whEl = document.getElementById('wh-state');
    const climateEl = document.getElementById('climate-state');
    const overrideEl = document.getElementById('override-state');

    // Water heater state with nice formatting
    const whState = currentData.waterHeaterState || '--';
    whEl.textContent = whState.replace(/_/g, ' ');
    if (whState === 'off') {
        whEl.style.color = '#a0aec0';
    } else if (whState === 'heat_pump' || whState === 'performance') {
        whEl.style.color = '#68d391';
    } else {
        whEl.style.color = '#00d9ff';
    }

    // Climate state
    const climateState = currentData.climateState || '--';
    climateEl.textContent = climateState.replace(/_/g, ' ');
    if (climateState === 'off') {
        climateEl.style.color = '#a0aec0';
    } else if (climateState === 'heat' || climateState === 'auto') {
        climateEl.style.color = '#68d391';
    } else {
        climateEl.style.color = '#00d9ff';
    }

    // Override state
    overrideEl.textContent = currentData.manualOverride ? 'Active' : 'Off';
    overrideEl.style.color = currentData.manualOverride ? '#ed8936' : '#68d391';
}

/**
 * Update fake heating alert
 */
function updateFakeHeatingAlert() {
    const alertEl = document.getElementById('fake-heating-alert');
    alertEl.style.display = currentData.fakeHeating ? 'flex' : 'none';
}

/**
 * Update override alert
 */
function updateOverrideAlert() {
    const alertEl = document.getElementById('override-alert');
    alertEl.style.display = currentData.manualOverride ? 'flex' : 'none';
}

/**
 * Update action history
 */
function updateActionHistory(history) {
    const container = document.getElementById('action-history');

    if (!history || history.length === 0) {
        container.innerHTML = '<div class="empty-state"><span class="mdi mdi-history"></span><p>No actions recorded yet</p></div>';
        return;
    }

    const items = history.slice(-10).reverse().map(item => {
        const time = new Date(item.timestamp).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
        const icon = item.action.includes('cwu') ? 'mdi-water-boiler' :
                    item.action.includes('floor') ? 'mdi-heating-coil' :
                    item.action.includes('enable') ? 'mdi-power' :
                    item.action.includes('disable') ? 'mdi-power-off' : 'mdi-chevron-right';

        return `
            <div class="history-item">
                <span class="history-time">${time}</span>
                <span class="history-icon mdi ${icon}"></span>
                <span class="history-text">${item.action}</span>
            </div>
        `;
    }).join('');

    container.innerHTML = items;
}

/**
 * Update state history
 */
function updateStateHistory(history) {
    const container = document.getElementById('state-history');

    if (!history || history.length === 0) {
        container.innerHTML = '<div class="empty-state"><span class="mdi mdi-timeline-clock"></span><p>No state changes recorded yet</p></div>';
        return;
    }

    const items = history.slice(-10).reverse().map(item => {
        const time = new Date(item.timestamp).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
        const stateClass = item.to_state.includes('cwu') ? 'cwu' :
                          item.to_state.includes('floor') ? 'floor' :
                          item.to_state.includes('pause') ? 'pause' :
                          item.to_state.includes('emergency') ? 'emergency' : '';

        const icon = STATE_ICONS[item.to_state] || 'mdi-circle';

        return `
            <div class="timeline-item ${stateClass}">
                <div class="timeline-marker">
                    <span class="mdi ${icon}"></span>
                </div>
                <div class="timeline-content">
                    <span class="timeline-time">${time}</span>
                    <p class="timeline-transition">
                        ${item.from_state.replace(/_/g, ' ')} → <strong>${item.to_state.replace(/_/g, ' ')}</strong>
                    </p>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = items;
}

/**
 * Initialize Chart.js charts
 */
function initCharts() {
    // Common chart options
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
            mode: 'index',
            intersect: false,
        },
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    color: '#e2e8f0',
                    usePointStyle: true,
                    padding: 20,
                    font: {
                        family: "'Inter', sans-serif",
                        size: 12,
                    }
                }
            },
            tooltip: {
                backgroundColor: 'rgba(26, 32, 44, 0.9)',
                titleColor: '#e2e8f0',
                bodyColor: '#a0aec0',
                borderColor: 'rgba(255, 255, 255, 0.1)',
                borderWidth: 1,
                cornerRadius: 8,
                padding: 12,
            }
        },
        scales: {
            x: {
                type: 'time',
                time: {
                    displayFormats: {
                        hour: 'HH:mm',
                        minute: 'HH:mm',
                    }
                },
                grid: {
                    color: 'rgba(255, 255, 255, 0.05)',
                },
                ticks: {
                    color: '#a0aec0',
                    font: {
                        size: 11,
                    }
                }
            },
            y: {
                grid: {
                    color: 'rgba(255, 255, 255, 0.05)',
                },
                ticks: {
                    color: '#a0aec0',
                    font: {
                        size: 11,
                    }
                }
            }
        }
    };

    // Temperature chart
    const tempCtx = document.getElementById('tempChart').getContext('2d');
    tempChart = new Chart(tempCtx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'CWU',
                    data: [],
                    borderColor: '#00d9ff',
                    backgroundColor: 'rgba(0, 217, 255, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                },
                {
                    label: 'Living Room',
                    data: [],
                    borderColor: '#68d391',
                    backgroundColor: 'rgba(104, 211, 145, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                },
                {
                    label: 'Bedroom',
                    data: [],
                    borderColor: '#ed8936',
                    backgroundColor: 'rgba(237, 137, 54, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                },
                {
                    label: 'Kids Room',
                    data: [],
                    borderColor: '#9f7aea',
                    backgroundColor: 'rgba(159, 122, 234, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                }
            ]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    suggestedMin: 15,
                    suggestedMax: 50,
                    title: {
                        display: true,
                        text: 'Temperature (°C)',
                        color: '#a0aec0',
                    }
                }
            }
        }
    });

    // Power chart
    const powerCtx = document.getElementById('powerChart').getContext('2d');
    powerChart = new Chart(powerCtx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Power',
                    data: [],
                    borderColor: '#fc8181',
                    backgroundColor: 'rgba(252, 129, 129, 0.2)',
                    borderWidth: 2,
                    tension: 0.2,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                }
            ]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    suggestedMin: 0,
                    suggestedMax: 1500,
                    title: {
                        display: true,
                        text: 'Power (W)',
                        color: '#a0aec0',
                    }
                }
            }
        }
    });
}

/**
 * Update chart data from history
 */
async function updateChartData() {
    const hoursMap = {
        '1h': 1,
        '6h': 6,
        '24h': 24,
    };

    const hours = hoursMap[CONFIG.chartRange] || 6;

    // Fetch history for all entities in parallel
    const [cwuHistory, salonHistory, bedroomHistory, kidsHistory, powerHistory] = await Promise.all([
        fetchHistory(EXTERNAL_ENTITIES.cwuTemp, hours),
        fetchHistory(EXTERNAL_ENTITIES.salonTemp, hours),
        fetchHistory(EXTERNAL_ENTITIES.bedroomTemp, hours),
        fetchHistory(EXTERNAL_ENTITIES.kidsTemp, hours),
        fetchHistory(EXTERNAL_ENTITIES.power, hours),
    ]);

    // Convert history to chart data format
    const convertToChartData = (history) => {
        return history
            .filter(item => item.state !== 'unavailable' && item.state !== 'unknown')
            .map(item => ({
                x: new Date(item.last_changed || item.last_updated),
                y: parseFloat(item.state)
            }))
            .filter(item => !isNaN(item.y));
    };

    // Update temperature chart
    if (tempChart) {
        tempChart.data.datasets[0].data = convertToChartData(cwuHistory);
        tempChart.data.datasets[1].data = convertToChartData(salonHistory);
        tempChart.data.datasets[2].data = convertToChartData(bedroomHistory);
        tempChart.data.datasets[3].data = convertToChartData(kidsHistory);
        tempChart.update('none');
    }

    // Update power chart
    if (powerChart) {
        powerChart.data.datasets[0].data = convertToChartData(powerHistory);
        powerChart.update('none');
    }
}

/**
 * Update chart time range
 */
function updateChartRange(range) {
    CONFIG.chartRange = range;

    // Update button states
    document.querySelectorAll('.chart-controls .btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Refresh chart data
    updateChartData();
}

/**
 * Toggle controller on/off
 */
async function toggleController() {
    const isEnabled = document.getElementById('controller-toggle').checked;
    const service = isEnabled ? 'enable' : 'disable';
    await callService('cwu_controller', service);
}

/**
 * Force CWU heating
 */
async function forceCWU(duration) {
    const hours = duration / 60;
    if (confirm(`Force CWU heating for ${hours} hour${hours > 1 ? 's' : ''}? This will override automatic control.`)) {
        await callService('cwu_controller', 'force_cwu', { duration });
    }
}

/**
 * Force floor heating
 */
async function forceFloor(duration) {
    const hours = duration / 60;
    if (confirm(`Force floor heating for ${hours} hour${hours > 1 ? 's' : ''}? This will override automatic control.`)) {
        await callService('cwu_controller', 'force_floor', { duration });
    }
}

/**
 * Test action
 */
async function testAction(action) {
    const entityMap = {
        'cwu_on': 'button.cwu_controller_test_cwu_on',
        'cwu_off': 'button.cwu_controller_test_cwu_off',
        'floor_on': 'button.cwu_controller_test_floor_on',
        'floor_off': 'button.cwu_controller_test_floor_off',
    };

    const entityId = entityMap[action];
    if (entityId) {
        await callService('button', 'press', { entity_id: entityId });
    }
}

/**
 * Dismiss fake heating alert
 */
function dismissAlert() {
    document.getElementById('fake-heating-alert').style.display = 'none';
}

/**
 * Show notification
 */
function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container');

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span class="notification-icon mdi ${type === 'error' ? 'mdi-alert-circle' : type === 'success' ? 'mdi-check-circle' : 'mdi-information'} "></span>
        <span class="notification-message">${message}</span>
        <button class="notification-close" onclick="this.parentElement.remove()">
            <span class="mdi mdi-close"></span>
        </button>
    `;

    container.appendChild(notification);

    // Animate in
    setTimeout(() => notification.classList.add('show'), 10);

    // Remove after 5 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

/**
 * Update last update time display
 */
function updateLastUpdateTime() {
    const el = document.getElementById('last-update');
    if (el) {
        el.textContent = new Date().toLocaleTimeString('pl-PL', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', init);
