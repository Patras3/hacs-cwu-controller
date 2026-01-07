/**
 * CWU Controller Panel JavaScript v8.3
 * v3.0: Redesigned with compact state bar, mode selector, and integrated cycle timer
 * v4.0: Added tariff breakdown, token handling, safe_mode, winter emergency threshold
 * v6.0: Major release - Winter mode, Safe mode, G12w tariff tracking
 * v7.0: Mobile-first redesign - Quick stats widgets at top (Power, CWU Temp+State, Mini Power Chart)
 * v7.1: Added BSB-LAN heat pump status widget with live data from pump
 * v7.2: Fixed BSB-LAN - now fetches on-demand via dedicated API endpoint (not in background)
 * v7.3: BSB-LAN refactor - uses coordinator sensor entities instead of API requests
 * v8.0: Anti-oscillation UI (HP ready, hold times, max temp, night window), enhanced state display
 * v8.1: BSB-LAN only refactor - removed cloud entities, CWU/floor modes from BSB-LAN exclusively
 * v8.2: Added holographic system visualization card (heat pump, CWU tank, floor heating)
 * v8.3: Added Floor Boost UI - raise floor temp to 28°C for X hours or until session ends
 */

// Configuration
const CONFIG = {
    updateInterval: 5000,
    chartUpdateInterval: 60000,
    maxPower: 4500, // Max power with floor + compressor heater
    cwuMaxPower: 3200,
    cwuTypicalPower: 1500,
    pumpCirculatingPower: 80,
    idlePower: 10,
    cycleInterval: 7, // minutes between peaks
};

// Entity IDs
const ENTITIES = {
    state: 'sensor.cwu_controller_state',
    cwuUrgency: 'sensor.cwu_controller_cwu_urgency',
    floorUrgency: 'sensor.cwu_controller_floor_urgency',
    avgPower: 'sensor.cwu_controller_average_power',
    heatingTime: 'sensor.cwu_controller_cwu_heating_time',
    cwuTargetTemp: 'sensor.cwu_controller_cwu_target_temp',
    enabled: 'switch.cwu_controller_enabled',
    cwuHeating: 'binary_sensor.cwu_controller_cwu_heating',
    floorHeating: 'binary_sensor.cwu_controller_floor_heating',
    fakeHeating: 'binary_sensor.cwu_controller_fake_heating_detected',
    manualOverride: 'binary_sensor.cwu_controller_manual_override',
    // BSB-LAN sensors (fetched via coordinator, not direct API)
    bsbDhwStatus: 'sensor.cwu_controller_bsb_dhw_status',
    bsbHpStatus: 'sensor.cwu_controller_bsb_heat_pump_status',
    bsbHc1Status: 'sensor.cwu_controller_bsb_hc1_status',
    bsbCwuMode: 'sensor.cwu_controller_bsb_cwu_mode',
    bsbFloorMode: 'sensor.cwu_controller_bsb_floor_mode',
    bsbCwuTemp: 'sensor.cwu_controller_bsb_cwu_temperature',
    bsbFlowTemp: 'sensor.cwu_controller_bsb_flow_temperature',
    bsbReturnTemp: 'sensor.cwu_controller_bsb_return_temperature',
    bsbDeltaT: 'sensor.cwu_controller_bsb_delta_t',
    bsbOutsideTemp: 'sensor.cwu_controller_bsb_outside_temperature',
    bsbAvailable: 'binary_sensor.cwu_controller_bsb_lan_available',
    controlSource: 'sensor.cwu_controller_control_source',
};

const EXTERNAL_ENTITIES = {
    // Room temps (still from HA sensors)
    salonTemp: 'sensor.temperatura_govee_salon',
    bedroomTemp: 'sensor.temperatura_govee_sypialnia',
    kidsTemp: 'sensor.temperatura_govee_dzieciecy',
    power: 'sensor.ogrzewanie_total_system_power',
    // Technical temps
    pumpInlet: 'sensor.temperatura_wejscia_pompy_ciepla',
    pumpOutlet: 'sensor.temperatura_wyjscia_pompy_ciepla',
    cwuInlet: 'sensor.temperatura_wejscia_c_w_u',
    floorInlet: 'sensor.temperatura_wejscia_ogrzewania_podlogowego',
    // NOTE: CWU temp, water heater, climate removed - now using BSB-LAN exclusively
};

// State icons and classes
const STATE_ICONS = {
    'idle': 'mdi-sleep',
    'heating_cwu': 'mdi-water-boiler',
    'heating_floor': 'mdi-heating-coil',
    'pause': 'mdi-pause-circle',
    'emergency_cwu': 'mdi-water-boiler-alert',
    'emergency_floor': 'mdi-home-alert',
    'fake_heating_detected': 'mdi-alert-circle',
    'fake_heating_restarting': 'mdi-refresh-circle',
    'safe_mode': 'mdi-shield-check',
};

const STATE_CLASSES = {
    'heating_cwu': 'state-heating-cwu',
    'heating_floor': 'state-heating-floor',
    'emergency_cwu': 'state-emergency',
    'emergency_floor': 'state-emergency',
    'fake_heating_detected': 'state-emergency',
    'fake_heating_restarting': 'state-heating-cwu',
    'pause': 'state-pause',
    'safe_mode': 'state-safe-mode',
};

const STATE_DESCRIPTIONS = {
    'idle': 'System is monitoring, ready to act when needed',
    'heating_cwu': 'Actively heating CWU - minimum hold time before switching',
    'heating_floor': 'Actively heating floor - minimum hold time before switching',
    'pause': 'Mandatory 10-minute pause (3h cycle limit reached)',
    'emergency_cwu': 'Emergency! CWU temperature critically low - priority heating',
    'emergency_floor': 'Emergency! Room temperature critically low - priority heating',
    'fake_heating_detected': 'Fake heating detected - waiting for HP ready',
    'fake_heating_restarting': 'HP ready - restarting CWU heating',
    'safe_mode': 'Safe mode - BSB-LAN unavailable, using cloud backup',
};

const URGENCY_COLORS = ['#68d391', '#8BC34A', '#FF9800', '#FF5722', '#F44336'];
const URGENCY_LEVELS = ['None', 'Low', 'Medium', 'High', 'Critical'];

// Data storage
let currentData = {};
let updateTimer = null;
let chartUpdateTimer = null;
let tempChart = null;
let powerChart = null;
let techChart = null;
let outsideChart = null;
let modalChart = null;
let quickPowerChart = null;
let stateStartTime = null;
let cwuTemp1hAgo = null;

// Session energy (calculated from HA history)
let sessionEnergyKwh = 0;

// Chart ranges
let chartRanges = {
    tempChart: '6h',
    powerChart: '6h',
    techChart: '6h',
    outsideChart: '24h',
};
let modalChartType = 'temp';
let modalChartRange = '24h';

// Mode selection modal state
let selectedModeType = null; // 'cwu' or 'floor'
let selectedDuration = 3; // hours
let selectedModeTab = 'duration'; // 'duration' or 'heat-to'

/**
 * Initialize the panel
 */
async function init() {
    console.log('CWU Controller Panel v8.0 initializing...');

    document.getElementById('controller-toggle').addEventListener('change', toggleController);

    initCharts();
    initQuickPowerChart();
    await refreshData();
    await updateAllChartData();
    await updateQuickPowerChart();
    await fetchCwuTemp1hAgo();

    updateTimer = setInterval(refreshData, CONFIG.updateInterval);
    chartUpdateTimer = setInterval(updateAllChartData, CONFIG.chartUpdateInterval);
    // Update quick chart more frequently for real-time feel
    setInterval(updateQuickPowerChart, 30000);

    updateLastUpdateTime();
    setInterval(updateLastUpdateTime, 1000);

    console.log('CWU Controller Panel initialized');
}

// Token management
let cachedToken = null;
let tokenRefreshAttempts = 0;
const MAX_TOKEN_REFRESH_ATTEMPTS = 3;

/**
 * Get authentication token with caching and refresh support
 */
function getToken() {
    // Try to get fresh token from HA
    const freshToken = getFreshToken();
    if (freshToken) {
        cachedToken = freshToken;
        tokenRefreshAttempts = 0;
        return freshToken;
    }

    // Return cached token if available
    if (cachedToken) {
        return cachedToken;
    }

    // Fallback to URL params or localStorage
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('token') || localStorage.getItem('ha_token') || '';
}

/**
 * Get fresh token from Home Assistant
 */
function getFreshToken() {
    try {
        if (window.parent && window.parent.hassConnection) {
            return window.parent.hassConnection.options.auth.accessToken;
        }
    } catch (e) {}

    try {
        if (window.parent && window.parent.document) {
            const haMain = window.parent.document.querySelector('home-assistant');
            if (haMain && haMain.hass) {
                return haMain.hass.auth.data.access_token;
            }
        }
    } catch (e) {}

    return null;
}

/**
 * Handle authentication error (403)
 */
function handleAuthError() {
    tokenRefreshAttempts++;
    cachedToken = null; // Clear cached token

    if (tokenRefreshAttempts >= MAX_TOKEN_REFRESH_ATTEMPTS) {
        showAuthErrorBanner();
        return false;
    }

    // Try to get a fresh token
    const newToken = getFreshToken();
    if (newToken) {
        cachedToken = newToken;
        console.log('Token refreshed successfully');
        return true;
    }

    return false;
}

/**
 * Show authentication error banner
 */
function showAuthErrorBanner() {
    // Check if banner already exists
    if (document.getElementById('auth-error-banner')) return;

    const banner = document.createElement('div');
    banner.id = 'auth-error-banner';
    banner.className = 'alert alert-danger animated';
    banner.innerHTML = `
        <span class="alert-icon mdi mdi-shield-alert"></span>
        <div>
            <strong>Session Expired</strong>
            <p>Your authentication token has expired. Please refresh the page to continue.</p>
        </div>
        <button class="btn btn-sm" onclick="location.reload()">
            <span class="mdi mdi-refresh"></span> Refresh Page
        </button>
    `;
    banner.style.display = 'flex';

    // Insert after header
    const header = document.querySelector('.header');
    if (header && header.nextSibling) {
        header.parentNode.insertBefore(banner, header.nextSibling);
    } else {
        document.querySelector('.container').prepend(banner);
    }

    // Stop update timers
    if (updateTimer) clearInterval(updateTimer);
    if (chartUpdateTimer) clearInterval(chartUpdateTimer);

    // Update connection state
    document.getElementById('connection-state').textContent = 'Auth Error';
    document.getElementById('connection-state').style.color = '#fc8181';
}

/**
 * Fetch entity state with auth error handling
 */
async function fetchState(entityId, retryOnAuth = true) {
    try {
        const response = await fetch(`/api/states/${entityId}`, {
            headers: {
                'Authorization': `Bearer ${getToken()}`,
                'Content-Type': 'application/json',
            },
        });

        // Handle 401/403 auth errors
        if (response.status === 401 || response.status === 403) {
            console.warn(`Auth error (${response.status}) fetching ${entityId}`);
            if (retryOnAuth && handleAuthError()) {
                // Retry with refreshed token
                return await fetchState(entityId, false);
            }
            return null;
        }

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`Failed to fetch ${entityId}:`, error);
        return null;
    }
}

/**
 * Fetch history data with auth error handling
 */
async function fetchHistory(entityId, hoursBack = 6, retryOnAuth = true) {
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

        // Handle 401/403 auth errors
        if (response.status === 401 || response.status === 403) {
            console.warn(`Auth error (${response.status}) fetching history for ${entityId}`);
            if (retryOnAuth && handleAuthError()) {
                return await fetchHistory(entityId, hoursBack, false);
            }
            return [];
        }

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        return data[0] || [];
    } catch (error) {
        console.error(`Failed to fetch history for ${entityId}:`, error);
        return [];
    }
}

/**
 * Fetch state history from HA history API and convert to our format
 * Returns array of {timestamp, from_state, to_state}
 */
async function fetchStateHistory(hoursBack = 24) {
    const history = await fetchHistory(ENTITIES.state, hoursBack);
    if (history.length < 2) return [];

    const stateChanges = [];
    for (let i = 1; i < history.length; i++) {
        const prev = history[i - 1];
        const curr = history[i];
        // Only record actual state changes
        if (prev.state !== curr.state) {
            stateChanges.push({
                timestamp: curr.last_changed || curr.last_updated,
                from_state: prev.state,
                to_state: curr.state,
            });
        }
    }
    return stateChanges;
}

/**
 * Build chart annotations from state history
 * Shows semi-transparent background bands for CWU (blue) and floor (orange) heating periods
 */
async function buildStateAnnotations(hoursBack) {
    const history = await fetchHistory(ENTITIES.state, hoursBack);
    if (history.length < 1) return {};

    const annotations = {};
    let annotationId = 0;

    // Colors for different states
    const stateColors = {
        'heating_cwu': 'rgba(0, 217, 255, 0.15)',      // CWU - cyan/blue
        'emergency_cwu': 'rgba(0, 217, 255, 0.25)',    // Emergency CWU - brighter
        'heating_floor': 'rgba(237, 137, 54, 0.15)',   // Floor - orange
        'emergency_floor': 'rgba(237, 137, 54, 0.25)', // Emergency floor - brighter
        'pause': 'rgba(160, 174, 192, 0.1)',           // Pause - gray
    };

    // Build periods from state changes
    for (let i = 0; i < history.length; i++) {
        const state = history[i].state;
        const color = stateColors[state];
        if (!color) continue; // Skip idle and other states

        const startTime = new Date(history[i].last_changed || history[i].last_updated);
        // End time is next state change or now
        const endTime = (i + 1 < history.length)
            ? new Date(history[i + 1].last_changed || history[i + 1].last_updated)
            : new Date();

        annotations[`state_${annotationId++}`] = {
            type: 'box',
            xMin: startTime,
            xMax: endTime,
            backgroundColor: color,
            borderWidth: 0,
            drawTime: 'beforeDatasetsDraw',
        };
    }

    return annotations;
}

/**
 * Fetch CWU temp from 1 hour ago for comparison (now from BSB-LAN sensor)
 */
async function fetchCwuTemp1hAgo() {
    const history = await fetchHistory(ENTITIES.bsbCwuTemp, 1.5);
    if (history.length > 0) {
        // Find temp closest to 1 hour ago
        const oneHourAgo = Date.now() - 60 * 60 * 1000;
        let closest = history[0];
        let minDiff = Infinity;

        for (const item of history) {
            const itemTime = new Date(item.last_changed || item.last_updated).getTime();
            const diff = Math.abs(itemTime - oneHourAgo);
            if (diff < minDiff) {
                minDiff = diff;
                closest = item;
            }
        }

        cwuTemp1hAgo = parseFloat(closest.state);
    }
}

/**
 * Calculate session energy from HA power history
 * @param {string} sessionStartTime - ISO timestamp of session start
 * @returns {Promise<number>} Energy in kWh
 */
async function calculateSessionEnergy(sessionStartTime) {
    if (!sessionStartTime) return 0;

    const startTime = new Date(sessionStartTime);
    const now = new Date();
    const hoursBack = (now.getTime() - startTime.getTime()) / 3600000;

    // Fetch power history for session duration (max 4h to be safe)
    const history = await fetchHistory(EXTERNAL_ENTITIES.power, Math.min(hoursBack + 0.5, 4));

    if (history.length < 2) return 0;

    // Filter to only include readings from session start
    const sessionHistory = history.filter(item => {
        const itemTime = new Date(item.last_changed || item.last_updated).getTime();
        return itemTime >= startTime.getTime();
    });

    if (sessionHistory.length < 2) return 0;

    // Calculate energy using trapezoidal integration
    let totalWh = 0;
    for (let i = 1; i < sessionHistory.length; i++) {
        const prevItem = sessionHistory[i - 1];
        const currItem = sessionHistory[i];

        const prevTime = new Date(prevItem.last_changed || prevItem.last_updated).getTime();
        const currTime = new Date(currItem.last_changed || currItem.last_updated).getTime();
        const prevPower = parseFloat(prevItem.state) || 0;
        const currPower = parseFloat(currItem.state) || 0;

        // Hours between readings
        const hours = (currTime - prevTime) / 3600000;
        // Average power * time = Wh
        const avgPower = (prevPower + currPower) / 2;
        totalWh += avgPower * hours;
    }

    return totalWh / 1000; // Convert to kWh
}

/**
 * Call Home Assistant service with auth error handling
 */
async function callService(domain, service, data = {}, retryOnAuth = true) {
    try {
        const response = await fetch(`/api/services/${domain}/${service}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${getToken()}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });

        // Handle 401/403 auth errors
        if (response.status === 401 || response.status === 403) {
            console.warn(`Auth error (${response.status}) calling ${domain}.${service}`);
            if (retryOnAuth && handleAuthError()) {
                return await callService(domain, service, data, false);
            }
            showNotification('Session expired. Please refresh the page.', 'error');
            return false;
        }

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
        const stateData = await fetchState(ENTITIES.state);
        if (stateData) {
            if (currentData.state !== stateData.state) {
                stateStartTime = new Date();
                // Check for CWU session start/end
                handleCwuSessionChange(currentData.state, stateData.state);
            }
            currentData.state = stateData.state;
            currentData.attributes = stateData.attributes || {};
        }

        const [urgencyCwu, urgencyFloor, avgPower, heatingTime, cwuTargetTemp, enabled, fakeHeating, override, cwuHeating, floorHeating] = await Promise.all([
            fetchState(ENTITIES.cwuUrgency),
            fetchState(ENTITIES.floorUrgency),
            fetchState(ENTITIES.avgPower),
            fetchState(ENTITIES.heatingTime),
            fetchState(ENTITIES.cwuTargetTemp),
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
        if (cwuTargetTemp) {
            currentData.cwuTargetTemp = parseFloat(cwuTargetTemp.state) || 45;
            // Get min temp from attributes if available
            currentData.cwuMinTemp = parseFloat(cwuTargetTemp.attributes?.cwu_min_temp) || 35;
        }
        if (enabled) currentData.enabled = enabled.state === 'on';
        if (fakeHeating) currentData.fakeHeating = fakeHeating.state === 'on';
        if (override) currentData.manualOverride = override.state === 'on';
        if (cwuHeating) currentData.cwuHeatingActive = cwuHeating.state === 'on';
        if (floorHeating) currentData.floorHeatingActive = floorHeating.state === 'on';

        // Fetch external entities (room temps, power, technical temps)
        // NOTE: CWU temp now from BSB-LAN, water heater/climate states from BSB modes
        const [salonTemp, bedroomTemp, kidsTemp, power, pumpInlet, pumpOutlet, cwuInlet, floorInlet] = await Promise.all([
            fetchState(EXTERNAL_ENTITIES.salonTemp),
            fetchState(EXTERNAL_ENTITIES.bedroomTemp),
            fetchState(EXTERNAL_ENTITIES.kidsTemp),
            fetchState(EXTERNAL_ENTITIES.power),
            fetchState(EXTERNAL_ENTITIES.pumpInlet),
            fetchState(EXTERNAL_ENTITIES.pumpOutlet),
            fetchState(EXTERNAL_ENTITIES.cwuInlet),
            fetchState(EXTERNAL_ENTITIES.floorInlet),
        ]);

        if (salonTemp) currentData.salonTemp = parseFloat(salonTemp.state);
        if (bedroomTemp) currentData.bedroomTemp = parseFloat(bedroomTemp.state);
        if (kidsTemp) currentData.kidsTemp = parseFloat(kidsTemp.state);
        if (power) {
            currentData.power = parseFloat(power.state) || 0;
        }
        if (pumpInlet) currentData.pumpInlet = parseFloat(pumpInlet.state);
        if (pumpOutlet) currentData.pumpOutlet = parseFloat(pumpOutlet.state);
        if (cwuInlet) currentData.cwuInlet = parseFloat(cwuInlet.state);
        if (floorInlet) currentData.floorInlet = parseFloat(floorInlet.state);

        // Fetch BSB-LAN sensor data (from coordinator, not direct API)
        const [bsbDhwStatus, bsbHpStatus, bsbHc1Status, bsbCwuMode, bsbFloorMode, bsbCwuTemp, bsbFlowTemp, bsbReturnTemp, bsbDeltaT, bsbOutsideTemp, bsbAvailable, controlSource] = await Promise.all([
            fetchState(ENTITIES.bsbDhwStatus),
            fetchState(ENTITIES.bsbHpStatus),
            fetchState(ENTITIES.bsbHc1Status),
            fetchState(ENTITIES.bsbCwuMode),
            fetchState(ENTITIES.bsbFloorMode),
            fetchState(ENTITIES.bsbCwuTemp),
            fetchState(ENTITIES.bsbFlowTemp),
            fetchState(ENTITIES.bsbReturnTemp),
            fetchState(ENTITIES.bsbDeltaT),
            fetchState(ENTITIES.bsbOutsideTemp),
            fetchState(ENTITIES.bsbAvailable),
            fetchState(ENTITIES.controlSource),
        ]);

        // Update BSB-LAN display with sensor data
        const bsbData = {
            dhw_status: bsbDhwStatus?.state || '---',
            hp_status: bsbHpStatus?.state || '---',
            hc1_status: bsbHc1Status?.state || '---',
            cwu_mode: bsbCwuMode?.state || '---',
            cwu_mode_on: bsbCwuMode?.attributes?.is_on || false,
            floor_mode: bsbFloorMode?.state || '---',
            floor_mode_on: bsbFloorMode?.attributes?.is_on || false,
            cwu_temp: parseFloat(bsbCwuTemp?.state) || 0,
            flow_temp: parseFloat(bsbFlowTemp?.state) || 0,
            return_temp: parseFloat(bsbReturnTemp?.state) || 0,
            delta_t: parseFloat(bsbDeltaT?.state) || null,
            outside_temp: parseFloat(bsbOutsideTemp?.state) || 0,
            available: bsbAvailable?.state === 'on',
            control_source: controlSource?.state || 'unknown',
        };
        currentData.bsbLan = bsbData;

        // CWU temp now exclusively from BSB-LAN
        if (bsbCwuTemp && !isNaN(parseFloat(bsbCwuTemp.state))) {
            currentData.cwuTemp = parseFloat(bsbCwuTemp.state);
        }

        // Use BSB modes for display (instead of cloud entity states)
        currentData.waterHeaterState = bsbData.cwu_mode;   // CWU mode from BSB (On/Off/Eco)
        currentData.climateState = bsbData.floor_mode;      // Floor mode from BSB (Automatic/Protection/etc.)

        updateBsbLanDisplay(bsbData);

        document.getElementById('connection-state').textContent = 'Connected';
        document.getElementById('connection-state').style.color = '#68d391';

        await updateUI();
    } catch (error) {
        console.error('Failed to refresh data:', error);
        document.getElementById('connection-state').textContent = 'Error';
        document.getElementById('connection-state').style.color = '#fc8181';
    }
}

// Cached power stats (fetched from HA history)
let cachedPowerStats = { avg: 0, peak: 0, hasPeaks: false };
let lastPowerStatsFetch = 0;

/**
 * Fetch power statistics from HA history for last 10 minutes
 */
async function fetchPowerStats() {
    const now = Date.now();
    // Fetch every 30 seconds to avoid API spam
    if (now - lastPowerStatsFetch < 30000) {
        return cachedPowerStats;
    }
    lastPowerStatsFetch = now;

    try {
        const history = await fetchHistory(EXTERNAL_ENTITIES.power, 0.2); // ~12 minutes

        if (history.length < 2) {
            return cachedPowerStats;
        }

        // Filter to last 10 minutes
        const tenMinAgo = now - 10 * 60 * 1000;
        const recentHistory = history.filter(item => {
            const itemTime = new Date(item.last_changed || item.last_updated).getTime();
            return itemTime >= tenMinAgo;
        });

        if (recentHistory.length === 0) {
            return cachedPowerStats;
        }

        const powers = recentHistory.map(item => parseFloat(item.state) || 0);
        const avg = powers.reduce((a, b) => a + b, 0) / powers.length;
        const peak = Math.max(...powers);
        const hasPeaks = peak > 500;

        cachedPowerStats = { avg: Math.round(avg), peak: Math.round(peak), hasPeaks };
        return cachedPowerStats;
    } catch (error) {
        console.error('Failed to fetch power stats:', error);
        return cachedPowerStats;
    }
}

/**
 * Get cached power statistics (sync version for UI)
 */
function getPowerStats() {
    return cachedPowerStats;
}

/**
 * Handle CWU session state change
 */
function handleCwuSessionChange(oldState, newState) {
    if (newState === 'heating_cwu' && oldState !== 'heating_cwu') {
        // Session started - reset cached energy
        sessionEnergyKwh = 0;
        lastEnergyCalcTime = 0; // Force recalculation
        console.log('CWU Session started (tracked by backend)');
    } else if (oldState === 'heating_cwu' && newState !== 'heating_cwu') {
        console.log('CWU Session ended');
    }
}

/**
 * Update all UI elements
 */
async function updateUI() {
    const attrs = currentData.attributes || {};

    updateQuickStats();
    updateBsbLanDisplay();
    updateSystemVisualization();
    updateControllerStatus();
    updateStateDisplay();
    updateHeatingIndicators();
    updateOperatingModeDisplay();
    updateEnergyDisplay();
    await updateCwuSessionCard();

    updateTemperature('temp-cwu', currentData.cwuTemp || attrs.cwu_temp, currentData.cwuTargetTemp || 45, currentData.cwuMinTemp || 35);
    updateTemperature('temp-salon', currentData.salonTemp || attrs.salon_temp, 22, 19);
    updateTemperature('temp-bedroom', currentData.bedroomTemp || attrs.bedroom_temp, 20, 19);
    updateTemperature('temp-kids', currentData.kidsTemp || attrs.kids_temp, 20, 19);
    updateTempStatus();

    updateUrgencyGauge('cwu', currentData.cwuUrgency || 0);
    updateUrgencyGauge('floor', currentData.floorUrgency || 0);

    // Fetch power stats from HA history (cached, updates every 30s)
    await fetchPowerStats();

    updatePowerDisplay(currentData.power || attrs.power, currentData.avgPower);
    updateHeatPumpStatus();
    updateFakeHeatingAlert();
    updateOverrideAlert();

    updateActionHistory(attrs.action_history || []);
    // State history from HA history API (not coordinator attributes)
    const stateHistory = await fetchStateHistory(24);
    updateStateHistory(stateHistory);
    updateHeatToProgress();
}

/**
 * Update operating mode display
 */
function updateOperatingModeDisplay() {
    const attrs = currentData.attributes || {};
    const mode = attrs.operating_mode || 'broken_heater';
    const isCheapTariff = attrs.is_cheap_tariff || false;
    const tariffRate = attrs.current_tariff_rate || 0;
    const tariffCheapRate = attrs.tariff_cheap_rate || 0.72;
    const tariffExpensiveRate = attrs.tariff_expensive_rate || 1.16;
    const isHeatingWindow = attrs.is_cwu_heating_window || false;

    // Update mode selector
    const modeSelect = document.getElementById('operating-mode-select');
    if (modeSelect && modeSelect.value !== mode) {
        modeSelect.value = mode;
    }

    // Update tariff status badge
    const tariffStatus = document.getElementById('tariff-status');
    if (tariffStatus) {
        if (isCheapTariff) {
            tariffStatus.textContent = 'Cheap Tariff';
            tariffStatus.className = 'badge badge-success';
        } else {
            tariffStatus.textContent = 'Expensive Tariff';
            tariffStatus.className = 'badge badge-warning';
        }
    }

    // Update tariff rate
    const rateEl = document.getElementById('current-tariff-rate');
    if (rateEl) {
        rateEl.textContent = tariffRate.toFixed(2);
    }

    // Update configured tariff rates
    const cheapRateEl = document.getElementById('tariff-cheap-rate');
    const expensiveRateEl = document.getElementById('tariff-expensive-rate');
    if (cheapRateEl) {
        cheapRateEl.textContent = tariffCheapRate.toFixed(2);
    }
    if (expensiveRateEl) {
        expensiveRateEl.textContent = tariffExpensiveRate.toFixed(2);
    }

    // Show/hide winter mode specific info (heating window status)
    const heatingWindowRow = document.getElementById('heating-window-row');

    if (mode === 'winter') {
        if (heatingWindowRow) {
            heatingWindowRow.style.display = 'flex';
            const statusEl = document.getElementById('heating-window-status');
            if (statusEl) {
                statusEl.textContent = isHeatingWindow ? 'CWU heating window active' : 'Outside heating window';
                statusEl.style.color = isHeatingWindow ? '#68d391' : '#a0aec0';
            }
        }
    } else {
        if (heatingWindowRow) heatingWindowRow.style.display = 'none';
    }
}

/**
 * Update energy consumption display
 */
function updateEnergyDisplay() {
    const attrs = currentData.attributes || {};

    // Today - main totals
    const todayCwu = attrs.energy_today_cwu_kwh || 0;
    const todayFloor = attrs.energy_today_floor_kwh || 0;
    const todayTotal = attrs.energy_today_total_kwh || 0;
    const costToday = attrs.cost_today_estimate || 0;

    // Today - tariff breakdown
    const todayCwuCheap = attrs.energy_today_cwu_cheap_kwh || 0;
    const todayCwuExpensive = attrs.energy_today_cwu_expensive_kwh || 0;
    const todayFloorCheap = attrs.energy_today_floor_cheap_kwh || 0;
    const todayFloorExpensive = attrs.energy_today_floor_expensive_kwh || 0;
    const costTodayCwu = attrs.cost_today_cwu_estimate || 0;
    const costTodayFloor = attrs.cost_today_floor_estimate || 0;

    document.getElementById('energy-today-cwu').textContent = `${todayCwu.toFixed(2)} kWh`;
    document.getElementById('energy-today-cwu-cheap').textContent = `${todayCwuCheap.toFixed(2)} kWh`;
    document.getElementById('energy-today-cwu-expensive').textContent = `${todayCwuExpensive.toFixed(2)} kWh`;
    document.getElementById('energy-today-floor').textContent = `${todayFloor.toFixed(2)} kWh`;
    document.getElementById('energy-today-floor-cheap').textContent = `${todayFloorCheap.toFixed(2)} kWh`;
    document.getElementById('energy-today-floor-expensive').textContent = `${todayFloorExpensive.toFixed(2)} kWh`;
    document.getElementById('energy-today-total').textContent = `${todayTotal.toFixed(2)} kWh`;
    document.getElementById('cost-today').textContent = `~${costToday.toFixed(2)} zł`;
    document.getElementById('cost-today-cwu').textContent = `~${costTodayCwu.toFixed(2)} zł`;
    document.getElementById('cost-today-floor').textContent = `~${costTodayFloor.toFixed(2)} zł`;

    // Yesterday - main totals
    const yesterdayCwu = attrs.energy_yesterday_cwu_kwh || 0;
    const yesterdayFloor = attrs.energy_yesterday_floor_kwh || 0;
    const yesterdayTotal = attrs.energy_yesterday_total_kwh || 0;
    const costYesterday = attrs.cost_yesterday_estimate || 0;

    // Yesterday - tariff breakdown
    const yesterdayCwuCheap = attrs.energy_yesterday_cwu_cheap_kwh || 0;
    const yesterdayCwuExpensive = attrs.energy_yesterday_cwu_expensive_kwh || 0;
    const yesterdayFloorCheap = attrs.energy_yesterday_floor_cheap_kwh || 0;
    const yesterdayFloorExpensive = attrs.energy_yesterday_floor_expensive_kwh || 0;
    const costYesterdayCwu = attrs.cost_yesterday_cwu_estimate || 0;
    const costYesterdayFloor = attrs.cost_yesterday_floor_estimate || 0;

    document.getElementById('energy-yesterday-cwu').textContent = `${yesterdayCwu.toFixed(2)} kWh`;
    document.getElementById('energy-yesterday-cwu-cheap').textContent = `${yesterdayCwuCheap.toFixed(2)} kWh`;
    document.getElementById('energy-yesterday-cwu-expensive').textContent = `${yesterdayCwuExpensive.toFixed(2)} kWh`;
    document.getElementById('energy-yesterday-floor').textContent = `${yesterdayFloor.toFixed(2)} kWh`;
    document.getElementById('energy-yesterday-floor-cheap').textContent = `${yesterdayFloorCheap.toFixed(2)} kWh`;
    document.getElementById('energy-yesterday-floor-expensive').textContent = `${yesterdayFloorExpensive.toFixed(2)} kWh`;
    document.getElementById('energy-yesterday-total').textContent = `${yesterdayTotal.toFixed(2)} kWh`;
    document.getElementById('cost-yesterday').textContent = `~${costYesterday.toFixed(2)} zł`;
    document.getElementById('cost-yesterday-cwu').textContent = `~${costYesterdayCwu.toFixed(2)} zł`;
    document.getElementById('cost-yesterday-floor').textContent = `~${costYesterdayFloor.toFixed(2)} zł`;
}

/**
 * Change operating mode via HA service
 */
async function changeOperatingMode(mode) {
    if (!mode) return;

    const success = await callService('cwu_controller', 'set_mode', { mode: mode });
    if (success) {
        showNotification(`Operating mode changed to: ${mode.replace('_', ' ')}`, 'success');
    }
}

// Last energy calculation time (to avoid too many API calls)
let lastEnergyCalcTime = 0;

/**
 * Update CWU Session tracking card - uses backend session data
 */
async function updateCwuSessionCard() {
    const card = document.getElementById('cwu-session-card');
    const attrs = currentData.attributes || {};

    // Get session data from backend
    const sessionStartTime = attrs.cwu_session_start_time;
    const sessionStartTemp = attrs.cwu_session_start_temp;
    const heatingMinutes = attrs.cwu_heating_minutes || currentData.heatingTime || 0;

    // Check if session is active (have start time and currently heating CWU)
    const isActive = currentData.cwuHeatingActive && sessionStartTime;

    if (!isActive || sessionStartTemp === null || sessionStartTemp === undefined) {
        card.style.display = 'none';
        return;
    }

    card.style.display = 'block';

    // Calculate energy from history (every 30 seconds to avoid API spam)
    const now = Date.now();
    if (now - lastEnergyCalcTime > 30000) {
        lastEnergyCalcTime = now;
        sessionEnergyKwh = await calculateSessionEnergy(sessionStartTime);
    }

    const currentTemp = currentData.cwuTemp || sessionStartTemp;
    const tempChange = currentTemp - sessionStartTemp;
    const durationMin = heatingMinutes;
    const targetTemp = currentData.cwuTargetTemp || 45;
    const minTemp = currentData.cwuMinTemp || 35;

    // Calculate heating rate (°C per hour)
    const heatingRate = durationMin > 5 ? (tempChange / durationMin) * 60 : 0;

    // Estimate time to target
    const tempNeeded = targetTemp - currentTemp;
    let eta = '--';
    let etaTime = '--';
    let sessionsNeeded = '--';
    let tempAtSessionEnd = '--';

    if (heatingRate > 0.1) {
        const minutesToTarget = (tempNeeded / heatingRate) * 60;
        const etaDate = new Date(Date.now() + minutesToTarget * 60000);
        eta = formatDuration(minutesToTarget);
        etaTime = etaDate.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });

        // Temperature at session end (170 min max)
        const remainingSessionTime = 170 - heatingMinutes;
        const tempGainInSession = (heatingRate / 60) * remainingSessionTime;
        tempAtSessionEnd = (currentTemp + tempGainInSession).toFixed(1);

        // Sessions needed
        if (parseFloat(tempAtSessionEnd) < targetTemp) {
            const tempStillNeeded = targetTemp - parseFloat(tempAtSessionEnd);
            const tempPerSession = (heatingRate / 60) * 170 * 0.9; // 90% efficiency for pause
            sessionsNeeded = Math.ceil(tempStillNeeded / tempPerSession) + 1;
        } else {
            sessionsNeeded = 'This session';
        }
    }

    // Calculate progress
    const totalRange = targetTemp - minTemp;
    const progressPercent = Math.min(100, Math.max(0, ((currentTemp - minTemp) / totalRange) * 100));

    // Parse start time from ISO string
    const startTime = new Date(sessionStartTime);

    // Update UI elements
    document.getElementById('session-start-temp').textContent = `${sessionStartTemp?.toFixed(1) || '--'}°C`;
    document.getElementById('session-current-temp').textContent = `${currentTemp?.toFixed(1) || '--'}°C`;
    document.getElementById('session-temp-change').textContent = `${tempChange >= 0 ? '+' : ''}${tempChange.toFixed(1)}°C`;
    document.getElementById('session-temp-change').style.color = tempChange >= 0 ? '#68d391' : '#fc8181';
    document.getElementById('session-target-temp').textContent = `${targetTemp}°C`;

    document.getElementById('session-progress-fill').style.width = `${progressPercent}%`;
    document.getElementById('session-progress-percent').textContent = `${Math.round(progressPercent)}%`;

    document.getElementById('session-start-time').textContent = startTime.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
    document.getElementById('session-duration').textContent = formatDuration(durationMin);
    document.getElementById('session-rate').textContent = heatingRate > 0 ? heatingRate.toFixed(1) : '--';
    document.getElementById('session-eta').textContent = eta;

    // Energy consumption (from HA history)
    document.getElementById('session-energy').textContent = sessionEnergyKwh.toFixed(2);

    document.getElementById('forecast-completion').textContent = etaTime;
    document.getElementById('forecast-temp-at-end').textContent = `${tempAtSessionEnd}°C`;
    document.getElementById('forecast-sessions').textContent = sessionsNeeded;

    // 1h comparison
    if (cwuTemp1hAgo !== null) {
        const diff1h = currentTemp - cwuTemp1hAgo;
        document.getElementById('session-vs-1h').textContent = `${diff1h >= 0 ? '+' : ''}${diff1h.toFixed(1)}°C`;
        document.getElementById('session-vs-1h').style.color = diff1h >= 0 ? '#68d391' : '#fc8181';
    }

    // Update pump data from BSB-LAN
    updateSessionPumpData();

    // Update integrated cycle timer
    updateSessionCycleTimer(durationMin);
}

/**
 * Update heat pump data in session card (from BSB-LAN)
 */
function updateSessionPumpData() {
    const pumpDataEl = document.getElementById('session-pump-data');
    if (!pumpDataEl) return;

    const bsb = currentData.bsbLan;
    if (!bsb || !bsb.available) {
        pumpDataEl.style.display = 'none';
        return;
    }

    pumpDataEl.style.display = 'block';

    const cwuEl = document.getElementById('session-pump-cwu');
    const flowEl = document.getElementById('session-pump-flow');
    const returnEl = document.getElementById('session-pump-return');
    const deltaEl = document.getElementById('session-pump-delta');

    if (cwuEl) cwuEl.textContent = bsb.cwu_temp ? `${bsb.cwu_temp.toFixed(1)}°C` : '--°C';
    if (flowEl) flowEl.textContent = bsb.flow_temp ? `${bsb.flow_temp.toFixed(1)}°C` : '--°C';
    if (returnEl) returnEl.textContent = bsb.return_temp ? `${bsb.return_temp.toFixed(1)}°C` : '--°C';

    if (deltaEl) {
        const deltaT = bsb.delta_t !== null ? bsb.delta_t : (bsb.flow_temp && bsb.return_temp ? bsb.flow_temp - bsb.return_temp : null);
        if (deltaT !== null) {
            deltaEl.textContent = `${deltaT >= 0 ? '+' : ''}${deltaT.toFixed(1)}°C`;
            // Color based on delta T quality
            if (deltaT < 0) {
                deltaEl.style.color = '#fc8181'; // Bad - reversed flow
            } else if (deltaT >= 3 && deltaT <= 5) {
                deltaEl.style.color = '#68d391'; // Good
            } else if (deltaT > 0.5 && deltaT < 3) {
                deltaEl.style.color = '#ed8936'; // Warning
            } else if (deltaT <= 0.5) {
                deltaEl.style.color = '#fc8181'; // Bad - no flow
            } else {
                deltaEl.style.color = 'var(--accent-cyan)'; // High but ok
            }
        } else {
            deltaEl.textContent = '--°C';
        }
    }
}

/**
 * Update integrated cycle timer in session card
 */
function updateSessionCycleTimer(minutes) {
    const maxMinutes = 170;
    const mins = Math.round(minutes);
    const remaining = Math.max(0, maxMinutes - mins);
    const percentage = Math.min(mins / maxMinutes, 1);

    // Circumference of r=25 circle = 2 * PI * 25 = ~157
    const circumference = 157;
    const offset = circumference - (circumference * percentage);

    const progressEl = document.getElementById('session-cycle-progress');
    const timeEl = document.getElementById('session-cycle-time');
    const remainingEl = document.getElementById('session-cycle-remaining');
    const warningEl = document.getElementById('session-cycle-warning');

    if (progressEl) {
        progressEl.style.strokeDashoffset = offset;

        // Change color based on progress
        if (percentage > 0.9) {
            progressEl.style.stroke = '#fc8181';
        } else if (percentage > 0.7) {
            progressEl.style.stroke = '#ed8936';
        } else {
            progressEl.style.stroke = '#00d9ff';
        }
    }

    if (timeEl) timeEl.textContent = mins;
    if (remainingEl) remainingEl.textContent = remaining;
    if (warningEl) warningEl.style.display = percentage > 0.9 ? 'flex' : 'none';
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
    document.getElementById('cwu-indicator').className = `indicator ${currentData.cwuHeatingActive ? 'active cwu' : ''}`;
    document.getElementById('floor-indicator').className = `indicator ${currentData.floorHeatingActive ? 'active floor' : ''}`;
}

/**
 * Update state display (compact version)
 */
function updateStateDisplay() {
    const compactEl = document.getElementById('state-compact');
    const iconEl = document.getElementById('state-icon-sm');
    const nameEl = document.getElementById('state-name-sm');
    const durationEl = document.getElementById('state-duration-sm');

    const state = currentData.state || 'unknown';
    const attrs = currentData.attributes || {};
    const stateName = state.replace(/_/g, ' ');

    const iconClass = STATE_ICONS[state] || 'mdi-help-circle';
    iconEl.className = `state-icon-sm mdi ${iconClass}`;

    // Show state name with context info
    let displayName = stateName.charAt(0).toUpperCase() + stateName.slice(1);
    const holdTimeRemaining = attrs.hold_time_remaining || 0;

    // Add hold time info for heating states
    if (holdTimeRemaining > 0 && (state === 'heating_cwu' || state === 'heating_floor')) {
        displayName += ` (${Math.round(holdTimeRemaining)}m hold)`;
    }

    // Add HP status for fake heating states
    if (state === 'fake_heating_detected') {
        const hpReady = attrs.hp_ready !== false;
        if (!hpReady) {
            displayName += ` - ${attrs.hp_ready_reason || 'waiting'}`;
        }
    }

    nameEl.textContent = displayName;

    if (stateStartTime) {
        const now = new Date();
        const duration = Math.floor((now - stateStartTime) / 1000 / 60);
        durationEl.textContent = formatDuration(duration);
    } else {
        durationEl.textContent = '--';
    }

    // Apply state class for styling
    compactEl.className = 'state-compact';
    if (STATE_CLASSES[state]) compactEl.classList.add(STATE_CLASSES[state]);

    // Update mode buttons based on manual override
    updateModeButtons();
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

    const range = targetTemp - minTemp + 10;
    const progress = Math.min(100, Math.max(0, ((value - minTemp + 5) / range) * 100));
    if (barFill) barFill.style.width = `${progress}%`;

    let statusClass = 'good';
    if (elementId === 'temp-cwu') {
        if (value < 35) statusClass = 'critical';
        else if (value < 40) statusClass = 'warning';
    } else {
        if (value < 19) statusClass = 'critical';
        else if (value < 21) statusClass = 'warning';
    }

    el.className = `temp-item ${statusClass}`;

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
    const cwuMin = currentData.cwuMinTemp || 35;
    const temps = [
        { val: currentData.cwuTemp, min: cwuMin, warn: cwuMin + 5 },
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

    valueEl.textContent = value.toFixed(1);

    const percentage = Math.min(value / 4, 1);
    const offset = 377 - (377 * percentage);
    circle.style.strokeDashoffset = offset;

    const colorIndex = Math.min(Math.floor(value), 4);
    circle.style.stroke = URGENCY_COLORS[colorIndex];
    valueEl.style.color = URGENCY_COLORS[colorIndex];

    levelEl.textContent = URGENCY_LEVELS[colorIndex];
    levelEl.style.color = URGENCY_COLORS[colorIndex];
}

/**
 * Update power display with cycle awareness
 */
function updatePowerDisplay(power, avgPower) {
    const valueEl = document.getElementById('power-value');
    const barEl = document.getElementById('power-bar');
    const avgEl = document.getElementById('power-avg');
    const peakEl = document.getElementById('power-peak');
    const statusEl = document.getElementById('power-status');
    const indicatorEl = document.getElementById('power-indicator');
    const statusTextEl = document.getElementById('power-status-text');
    const cycleStatusEl = document.getElementById('power-cycle-status');
    const cycleInfoEl = document.getElementById('power-cycle-info');
    const cycleTextEl = document.getElementById('power-cycle-text');

    const powerVal = parseFloat(power) || 0;
    const powerStats = getPowerStats();

    valueEl.textContent = Math.round(powerVal);
    avgEl.textContent = powerStats.avg;
    peakEl.textContent = powerStats.peak;

    // Calculate bar width (max 4500W)
    const percentage = Math.min((powerVal / CONFIG.maxPower) * 100, 100);
    barEl.style.width = `${percentage}%`;

    // Determine status - use actual heating state, not just power thresholds
    let colorClass = 'idle';
    let statusText = 'Standby';
    let cycleStatus = 'Idle';
    let badgeClass = 'badge badge-secondary';

    // Determine heating type from actual state
    const isCwuHeating = currentData.cwuHeatingActive;
    const isFloorHeating = currentData.floorHeatingActive;
    const heatingType = isCwuHeating ? 'CWU' : isFloorHeating ? 'Floor' : null;

    if (powerVal < CONFIG.idlePower) {
        colorClass = 'idle';
        statusText = 'Standby';
        cycleStatus = 'Idle';
        badgeClass = 'badge badge-secondary';
    } else if (powerVal < 150) {
        // 80W range - pump circulating
        colorClass = powerStats.hasPeaks ? 'pump-active' : 'low';
        statusText = powerStats.hasPeaks ? 'Pump Circulating' : 'Low Power';
        cycleStatus = powerStats.hasPeaks ? 'Between Peaks' : 'Waiting';
        badgeClass = powerStats.hasPeaks ? 'badge badge-info' : 'badge badge-secondary';
    } else if (powerVal < 800) {
        colorClass = 'medium';
        statusText = heatingType ? `${heatingType} Ramping` : 'Ramping Up';
        cycleStatus = 'Starting';
        badgeClass = 'badge badge-warning';
    } else if (powerVal < 2000) {
        colorClass = 'high';
        statusText = heatingType ? `${heatingType} Heating` : 'Heating';
        cycleStatus = 'Active Peak';
        badgeClass = 'badge badge-success';
    } else if (powerVal < 3500) {
        colorClass = 'max';
        statusText = heatingType ? `${heatingType} High Power` : 'High Power';
        cycleStatus = isFloorHeating ? 'Max Floor' : 'Max CWU';
        badgeClass = 'badge badge-danger';
    } else {
        colorClass = 'extreme';
        statusText = 'Floor + CWU';
        cycleStatus = 'Full System';
        badgeClass = 'badge badge-danger';
    }

    barEl.className = `power-bar-fill ${colorClass}`;
    statusEl.textContent = `${Math.round(powerVal)}W`;
    statusEl.className = badgeClass;
    indicatorEl.className = `power-indicator ${colorClass}`;
    statusTextEl.textContent = statusText;
    cycleStatusEl.textContent = cycleStatus;

    // Update info text based on current mode
    if (currentData.cwuHeatingActive) {
        cycleTextEl.textContent = `CWU heating: peaks ~${CONFIG.cwuTypicalPower}W every ~${CONFIG.cycleInterval}min, ${CONFIG.pumpCirculatingPower}W = water circulating`;
    } else if (currentData.floorHeatingActive) {
        cycleTextEl.textContent = `Floor heating active. Max with compressor heater: ${CONFIG.maxPower}W`;
    } else {
        cycleTextEl.textContent = `System standby. Pump works in cycles when heating.`;
    }
}

/**
 * Update heat pump status
 */
function updateHeatPumpStatus() {
    const whEl = document.getElementById('wh-state');
    const climateEl = document.getElementById('climate-state');
    const overrideEl = document.getElementById('override-state');

    const whState = currentData.waterHeaterState || '--';
    whEl.textContent = whState.replace(/_/g, ' ');
    whEl.style.color = whState === 'off' ? '#a0aec0' : (whState === 'heat_pump' || whState === 'performance') ? '#68d391' : '#00d9ff';

    const climateState = currentData.climateState || '--';
    climateEl.textContent = climateState.replace(/_/g, ' ');
    climateEl.style.color = climateState === 'off' ? '#a0aec0' : (climateState === 'heat' || climateState === 'auto') ? '#68d391' : '#00d9ff';

    overrideEl.textContent = currentData.manualOverride ? 'Active' : 'Off';
    overrideEl.style.color = currentData.manualOverride ? '#ed8936' : '#68d391';
}

/**
 * Update alerts
 */
function updateFakeHeatingAlert() {
    document.getElementById('fake-heating-alert').style.display = currentData.fakeHeating ? 'flex' : 'none';
}

function updateOverrideAlert() {
    const alertEl = document.getElementById('override-alert');
    const remainingEl = document.getElementById('override-remaining');

    if (currentData.manualOverride) {
        alertEl.style.display = 'flex';
        // Update remaining time
        const attrs = currentData.attributes || {};
        const overrideUntil = attrs.manual_override_until;
        if (overrideUntil) {
            const remaining = getTimeRemaining(overrideUntil);
            remainingEl.textContent = remaining || 'expiring...';
        } else {
            remainingEl.textContent = '--';
        }
    } else {
        alertEl.style.display = 'none';
    }
}

/**
 * Update action history with relative time
 */
function updateActionHistory(history) {
    const container = document.getElementById('action-history');

    if (!history || history.length === 0) {
        container.innerHTML = '<div class="empty-state"><span class="mdi mdi-history"></span><p>No actions recorded yet</p></div>';
        return;
    }

    const items = history.slice(-10).reverse().map(item => {
        const time = new Date(item.timestamp);
        const relTime = getRelativeTime(time);
        const absTime = time.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
        const action = item.action.toLowerCase();
        const icon = action.includes('cwu') || action.includes('dhw') || action.includes('heat-to') ? 'mdi-water-boiler' :
                    action.includes('floor') ? 'mdi-heating-coil' :
                    action.includes('enable') ? 'mdi-power' :
                    action.includes('disable') ? 'mdi-power-off' :
                    action.includes('fake') ? 'mdi-alert' :
                    action.includes('rapid') ? 'mdi-water-thermometer-outline' : 'mdi-chevron-right';

        const reasoning = item.reasoning || '';
        const reasoningHtml = reasoning ?
            `<div class="history-reasoning">${reasoning}</div>` : '';

        return `
            <div class="history-item" onclick="showHistoryDetail('action', '${item.action}', '${item.timestamp}')">
                <span class="history-time" title="${absTime}">${relTime}</span>
                <span class="history-icon mdi ${icon}"></span>
                <div class="history-content">
                    <span class="history-text">${item.action}</span>
                    ${reasoningHtml}
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = items;
}

/**
 * Update state history with relative time
 */
function updateStateHistory(history) {
    const container = document.getElementById('state-history');

    if (!history || history.length === 0) {
        container.innerHTML = '<div class="empty-state"><span class="mdi mdi-timeline-clock"></span><p>No state changes recorded yet</p></div>';
        return;
    }

    const items = history.slice(-10).reverse().map(item => {
        const time = new Date(item.timestamp);
        const relTime = getRelativeTime(time);
        const absTime = time.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
        const stateClass = item.to_state.includes('cwu') ? 'cwu' :
                          item.to_state.includes('floor') ? 'floor' :
                          item.to_state.includes('pause') ? 'pause' :
                          item.to_state.includes('emergency') ? 'emergency' :
                          item.to_state.includes('safe_mode') ? 'safe_mode' : '';
        const icon = STATE_ICONS[item.to_state] || 'mdi-circle';

        return `
            <div class="timeline-item ${stateClass}" onclick="showHistoryDetail('state', '${item.from_state} → ${item.to_state}', '${item.timestamp}')">
                <div class="timeline-marker">
                    <span class="mdi ${icon}"></span>
                </div>
                <div class="timeline-content">
                    <span class="timeline-time" title="${absTime}">${relTime}</span>
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
 * Get relative time string
 */
function getRelativeTime(date) {
    const now = Date.now();
    const diff = now - date.getTime();
    const mins = Math.floor(diff / 60000);
    const hours = Math.floor(mins / 60);
    const days = Math.floor(hours / 24);

    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
}

/**
 * Format duration in minutes to readable string
 */
function formatDuration(minutes) {
    if (minutes < 1) return '<1m';
    if (minutes < 60) return `${Math.round(minutes)}m`;
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

/**
 * Initialize charts
 */
function initCharts() {
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    color: '#e2e8f0',
                    usePointStyle: true,
                    padding: 15,
                    font: { family: "'Inter', sans-serif", size: 11 }
                }
            },
            tooltip: {
                backgroundColor: 'rgba(26, 32, 44, 0.95)',
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
                time: { displayFormats: { hour: 'HH:mm', minute: 'HH:mm' } },
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#a0aec0', font: { size: 10 } }
            },
            y: {
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#a0aec0', font: { size: 10 } }
            }
        }
    };

    // Temperature chart
    tempChart = new Chart(document.getElementById('tempChart').getContext('2d'), {
        type: 'line',
        data: {
            datasets: [
                { label: 'CWU', data: [], borderColor: '#00d9ff', backgroundColor: 'rgba(0, 217, 255, 0.1)', borderWidth: 2, tension: 0.4, fill: true, pointRadius: 0 },
                { label: 'Living Room', data: [], borderColor: '#68d391', borderWidth: 2, tension: 0.4, pointRadius: 0 },
                { label: 'Bedroom', data: [], borderColor: '#ed8936', borderWidth: 2, tension: 0.4, pointRadius: 0 },
                { label: 'Kids Room', data: [], borderColor: '#9f7aea', borderWidth: 2, tension: 0.4, pointRadius: 0 }
            ]
        },
        options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, suggestedMin: 15, suggestedMax: 50 } } }
    });

    // Power chart
    powerChart = new Chart(document.getElementById('powerChart').getContext('2d'), {
        type: 'line',
        data: {
            datasets: [
                { label: 'Power', data: [], borderColor: '#fc8181', backgroundColor: 'rgba(252, 129, 129, 0.2)', borderWidth: 2, tension: 0.2, fill: true, pointRadius: 0 }
            ]
        },
        options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, suggestedMin: 0, suggestedMax: 2000 } } }
    });

    // Technical temps chart (BSB-LAN data)
    techChart = new Chart(document.getElementById('techChart').getContext('2d'), {
        type: 'line',
        data: {
            datasets: [
                { label: 'CWU', data: [], borderColor: '#00d9ff', borderWidth: 2, tension: 0.4, pointRadius: 0 },
                { label: 'Flow', data: [], borderColor: '#fc8181', borderWidth: 2, tension: 0.4, pointRadius: 0 },
                { label: 'Return', data: [], borderColor: '#68d391', borderWidth: 2, tension: 0.4, pointRadius: 0 },
                { label: 'ΔT', data: [], borderColor: '#f6e05e', borderWidth: 2, tension: 0.4, pointRadius: 0, yAxisID: 'y1' }
            ]
        },
        options: {
            ...commonOptions,
            plugins: { ...commonOptions.plugins, legend: { display: false } },
            scales: {
                ...commonOptions.scales,
                y: { ...commonOptions.scales.y, suggestedMin: 20, suggestedMax: 60, position: 'left' },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    suggestedMin: 0,
                    suggestedMax: 15,
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#f6e05e', callback: (v) => v + '°' },
                    title: { display: true, text: 'ΔT', color: '#f6e05e' }
                }
            }
        }
    });

    // Outside temperature chart
    outsideChart = new Chart(document.getElementById('outsideChart').getContext('2d'), {
        type: 'line',
        data: {
            datasets: [
                { label: 'Outside', data: [], borderColor: '#b794f4', backgroundColor: 'rgba(183, 148, 244, 0.1)', borderWidth: 2, tension: 0.4, pointRadius: 0, fill: true }
            ]
        },
        options: {
            ...commonOptions,
            plugins: { ...commonOptions.plugins, legend: { display: false } },
            scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, suggestedMin: -10, suggestedMax: 30 } }
        }
    });
}

/**
 * Update all chart data
 */
async function updateAllChartData() {
    await updateChartData('tempChart', chartRanges.tempChart);
    await updateChartData('powerChart', chartRanges.powerChart);
    await updateChartData('techChart', chartRanges.techChart);
    await updateChartData('outsideChart', chartRanges.outsideChart);
}

/**
 * Update chart data
 */
async function updateChartData(chartId, range) {
    const hoursMap = { '1h': 1, '6h': 6, '24h': 24, '48h': 48, '7d': 168 };
    const hours = hoursMap[range] || 6;

    const convertToChartData = (history) => {
        return history
            .filter(item => item.state !== 'unavailable' && item.state !== 'unknown')
            .map(item => ({ x: new Date(item.last_changed || item.last_updated), y: parseFloat(item.state) }))
            .filter(item => !isNaN(item.y));
    };

    // Helper to apply state annotations to chart
    const applyAnnotations = (chart, annotations) => {
        if (!chart.options.plugins.annotation) {
            chart.options.plugins.annotation = { annotations: {} };
        }
        chart.options.plugins.annotation.annotations = annotations;
    };

    if (chartId === 'tempChart' && tempChart) {
        const [cwu, salon, bedroom, kids, annotations] = await Promise.all([
            fetchHistory(ENTITIES.bsbCwuTemp, hours),
            fetchHistory(EXTERNAL_ENTITIES.salonTemp, hours),
            fetchHistory(EXTERNAL_ENTITIES.bedroomTemp, hours),
            fetchHistory(EXTERNAL_ENTITIES.kidsTemp, hours),
            buildStateAnnotations(hours),
        ]);
        tempChart.data.datasets[0].data = convertToChartData(cwu);
        tempChart.data.datasets[1].data = convertToChartData(salon);
        tempChart.data.datasets[2].data = convertToChartData(bedroom);
        tempChart.data.datasets[3].data = convertToChartData(kids);
        applyAnnotations(tempChart, annotations);
        tempChart.update('none');
    } else if (chartId === 'powerChart' && powerChart) {
        const [power, annotations] = await Promise.all([
            fetchHistory(EXTERNAL_ENTITIES.power, hours),
            buildStateAnnotations(hours),
        ]);
        powerChart.data.datasets[0].data = convertToChartData(power);
        applyAnnotations(powerChart, annotations);
        powerChart.update('none');
    } else if (chartId === 'techChart' && techChart) {
        const [cwu, flow, ret, deltaT, annotations] = await Promise.all([
            fetchHistory(ENTITIES.bsbCwuTemp, hours),
            fetchHistory(ENTITIES.bsbFlowTemp, hours),
            fetchHistory(ENTITIES.bsbReturnTemp, hours),
            fetchHistory(ENTITIES.bsbDeltaT, hours),
            buildStateAnnotations(hours),
        ]);
        techChart.data.datasets[0].data = convertToChartData(cwu);
        techChart.data.datasets[1].data = convertToChartData(flow);
        techChart.data.datasets[2].data = convertToChartData(ret);
        techChart.data.datasets[3].data = convertToChartData(deltaT);
        applyAnnotations(techChart, annotations);
        techChart.update('none');
    } else if (chartId === 'outsideChart' && outsideChart) {
        const outside = await fetchHistory(ENTITIES.bsbOutsideTemp, hours);
        outsideChart.data.datasets[0].data = convertToChartData(outside);
        outsideChart.update('none');
    }
}

/**
 * Update chart range
 */
function updateChartRange(chartId, range) {
    chartRanges[chartId] = range;

    // Update button states
    const container = event.target.closest('.chart-controls');
    container.querySelectorAll('.btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');

    updateChartData(chartId, range);
}

/**
 * Open fullscreen chart modal
 */
function openFullscreenChart(type) {
    modalChartType = type;
    const modal = document.getElementById('chart-modal');
    const title = document.getElementById('chart-modal-title');

    const titles = { temp: 'Temperature History', power: 'Power History', tech: 'Technical Temperatures' };
    title.textContent = titles[type] || 'Chart';

    modal.classList.add('open');

    // Initialize modal chart
    if (modalChart) modalChart.destroy();
    initModalChart(type);
    updateModalChartData();
}

/**
 * Initialize modal chart
 */
function initModalChart(type) {
    const ctx = document.getElementById('modalChart').getContext('2d');
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: {
                position: 'top',
                labels: { color: '#e2e8f0', usePointStyle: true, padding: 20, font: { size: 12 } }
            },
            tooltip: {
                backgroundColor: 'rgba(26, 32, 44, 0.95)',
                titleColor: '#e2e8f0',
                bodyColor: '#a0aec0',
            }
        },
        scales: {
            x: {
                type: 'time',
                time: { displayFormats: { hour: 'HH:mm', day: 'dd.MM' } },
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#a0aec0' }
            },
            y: {
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#a0aec0' }
            }
        }
    };

    let datasets = [];
    if (type === 'temp') {
        datasets = [
            { label: 'CWU', data: [], borderColor: '#00d9ff', backgroundColor: 'rgba(0, 217, 255, 0.1)', borderWidth: 2, tension: 0.4, fill: true, pointRadius: 0 },
            { label: 'Living Room', data: [], borderColor: '#68d391', borderWidth: 2, tension: 0.4, pointRadius: 0 },
            { label: 'Bedroom', data: [], borderColor: '#ed8936', borderWidth: 2, tension: 0.4, pointRadius: 0 },
            { label: 'Kids Room', data: [], borderColor: '#9f7aea', borderWidth: 2, tension: 0.4, pointRadius: 0 }
        ];
    } else if (type === 'power') {
        datasets = [
            { label: 'Power', data: [], borderColor: '#fc8181', backgroundColor: 'rgba(252, 129, 129, 0.2)', borderWidth: 2, tension: 0.2, fill: true, pointRadius: 0 }
        ];
    } else if (type === 'tech') {
        datasets = [
            { label: 'CWU', data: [], borderColor: '#00d9ff', borderWidth: 2, tension: 0.4, pointRadius: 0 },
            { label: 'Pump Inlet', data: [], borderColor: '#fc8181', borderWidth: 2, tension: 0.4, pointRadius: 0 },
            { label: 'Pump Outlet', data: [], borderColor: '#68d391', borderWidth: 2, tension: 0.4, pointRadius: 0 },
            { label: 'CWU Inlet', data: [], borderColor: '#ed8936', borderWidth: 2, tension: 0.4, pointRadius: 0 },
            { label: 'Floor Inlet', data: [], borderColor: '#9f7aea', borderWidth: 2, tension: 0.4, pointRadius: 0 }
        ];
    }

    modalChart = new Chart(ctx, { type: 'line', data: { datasets }, options: commonOptions });
}

/**
 * Update modal chart range
 */
function updateModalChartRange(range) {
    modalChartRange = range;

    document.querySelectorAll('#chart-modal .modal-controls .btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');

    updateModalChartData();
}

/**
 * Update modal chart data
 */
async function updateModalChartData() {
    const hoursMap = { '1h': 1, '6h': 6, '24h': 24, '48h': 48, '7d': 168 };
    const hours = hoursMap[modalChartRange] || 24;

    const convertToChartData = (history) => {
        return history
            .filter(item => item.state !== 'unavailable' && item.state !== 'unknown')
            .map(item => ({ x: new Date(item.last_changed || item.last_updated), y: parseFloat(item.state) }))
            .filter(item => !isNaN(item.y));
    };

    // Helper to apply state annotations to chart
    const applyAnnotations = (chart, annotations) => {
        if (!chart.options.plugins.annotation) {
            chart.options.plugins.annotation = { annotations: {} };
        }
        chart.options.plugins.annotation.annotations = annotations;
    };

    // Fetch annotations for all chart types
    const annotations = await buildStateAnnotations(hours);

    if (modalChartType === 'temp') {
        const [cwu, salon, bedroom, kids] = await Promise.all([
            fetchHistory(ENTITIES.bsbCwuTemp, hours),
            fetchHistory(EXTERNAL_ENTITIES.salonTemp, hours),
            fetchHistory(EXTERNAL_ENTITIES.bedroomTemp, hours),
            fetchHistory(EXTERNAL_ENTITIES.kidsTemp, hours),
        ]);
        modalChart.data.datasets[0].data = convertToChartData(cwu);
        modalChart.data.datasets[1].data = convertToChartData(salon);
        modalChart.data.datasets[2].data = convertToChartData(bedroom);
        modalChart.data.datasets[3].data = convertToChartData(kids);
    } else if (modalChartType === 'power') {
        const power = await fetchHistory(EXTERNAL_ENTITIES.power, hours);
        modalChart.data.datasets[0].data = convertToChartData(power);
    } else if (modalChartType === 'tech') {
        const [cwu, pumpIn, pumpOut, cwuIn, floorIn] = await Promise.all([
            fetchHistory(ENTITIES.bsbCwuTemp, hours),
            fetchHistory(EXTERNAL_ENTITIES.pumpInlet, hours),
            fetchHistory(EXTERNAL_ENTITIES.pumpOutlet, hours),
            fetchHistory(EXTERNAL_ENTITIES.cwuInlet, hours),
            fetchHistory(EXTERNAL_ENTITIES.floorInlet, hours),
        ]);
        modalChart.data.datasets[0].data = convertToChartData(cwu);
        modalChart.data.datasets[1].data = convertToChartData(pumpIn);
        modalChart.data.datasets[2].data = convertToChartData(pumpOut);
        modalChart.data.datasets[3].data = convertToChartData(cwuIn);
        modalChart.data.datasets[4].data = convertToChartData(floorIn);
    }
    applyAnnotations(modalChart, annotations);
    modalChart.update('none');
}

/**
 * Open history modal
 */
async function openHistoryModal(type) {
    const modal = document.getElementById('history-modal');
    const title = document.getElementById('history-modal-title');
    const content = document.getElementById('history-modal-content');

    title.textContent = type === 'actions' ? 'Action History' : 'State Timeline';

    // Show loading state
    content.innerHTML = '<div class="loading"><div class="spinner"></div><span>Loading...</span></div>';
    modal.classList.add('open');

    // Fetch history - actions from attributes, states from HA history API
    const attrs = currentData.attributes || {};
    let history;
    if (type === 'actions') {
        history = attrs.action_history || [];
    } else {
        history = await fetchStateHistory(48); // 48h for modal view
    }

    if (history.length === 0) {
        content.innerHTML = '<div class="empty-state"><span class="mdi mdi-history"></span><p>No history available</p></div>';
    } else {
        const items = history.slice().reverse().map(item => {
            const time = new Date(item.timestamp);
            const relTime = getRelativeTime(time);
            const absTime = time.toLocaleString('pl-PL');

            if (type === 'actions') {
                const actionLower = (item.action || '').toLowerCase();
                const icon = actionLower.includes('cwu') ? 'mdi-water-boiler' :
                            actionLower.includes('floor') ? 'mdi-heating-coil' : 'mdi-chevron-right';
                const reasoningHtml = item.reasoning ?
                    `<span class="history-reasoning">${item.reasoning}</span>` : '';
                return `
                    <div class="history-item-full">
                        <span class="history-icon mdi ${icon}"></span>
                        <div class="history-details">
                            <span class="history-action">${item.action}</span>
                            ${reasoningHtml}
                            <span class="history-time-full">${absTime} (${relTime})</span>
                        </div>
                    </div>
                `;
            } else {
                const stateClass = item.to_state.includes('cwu') ? 'cwu' :
                                  item.to_state.includes('floor') ? 'floor' :
                                  item.to_state.includes('pause') ? 'pause' :
                                  item.to_state.includes('emergency') ? 'emergency' :
                                  item.to_state.includes('safe_mode') ? 'safe_mode' : '';
                const icon = STATE_ICONS[item.to_state] || 'mdi-circle';
                return `
                    <div class="timeline-item-full ${stateClass}">
                        <div class="timeline-marker">
                            <span class="mdi ${icon}"></span>
                        </div>
                        <div class="timeline-details">
                            <span class="timeline-transition-full">${item.from_state.replace(/_/g, ' ')} → <strong>${item.to_state.replace(/_/g, ' ')}</strong></span>
                            <span class="timeline-time-full">${absTime} (${relTime})</span>
                        </div>
                    </div>
                `;
            }
        }).join('');

        content.innerHTML = items;
    }
}

/**
 * Show history detail (placeholder for future enhancement)
 */
function showHistoryDetail(type, text, timestamp) {
    const time = new Date(timestamp);
    showNotification(`${text} at ${time.toLocaleString('pl-PL')}`, 'info');
}

/**
 * Close modal
 */
function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('open');
}

/**
 * Controller toggle
 */
async function toggleController() {
    const isEnabled = document.getElementById('controller-toggle').checked;
    await callService('cwu_controller', isEnabled ? 'enable' : 'disable');
}

/**
 * Force CWU/Floor heating
 */
async function forceCWU(duration) {
    const hours = duration / 60;
    if (confirm(`Force CWU heating for ${hours}h?`)) {
        await callService('cwu_controller', 'force_cwu', { duration });
    }
}

async function forceFloor(duration) {
    const hours = duration / 60;
    if (confirm(`Force floor heating for ${hours}h?`)) {
        await callService('cwu_controller', 'force_floor', { duration });
    }
}

/**
 * Mode control functions
 */
function updateModeButtons() {
    const autoBtn = document.getElementById('mode-btn-auto');
    const cwuBtn = document.getElementById('mode-btn-cwu');
    const floorBtn = document.getElementById('mode-btn-floor');
    const cwuDuration = document.getElementById('mode-cwu-duration');
    const floorDuration = document.getElementById('mode-floor-duration');

    // Clear active states
    autoBtn.classList.remove('active');
    cwuBtn.classList.remove('active');
    floorBtn.classList.remove('active');
    cwuDuration.textContent = '';
    floorDuration.textContent = '';

    if (!currentData.manualOverride) {
        // Auto mode
        autoBtn.classList.add('active');
    } else {
        // Manual override - check which mode
        const attrs = currentData.attributes || {};
        const overrideUntil = attrs.manual_override_until;

        if (currentData.cwuHeatingActive || currentData.state === 'heating_cwu') {
            cwuBtn.classList.add('active');
            if (overrideUntil) {
                const remaining = getTimeRemaining(overrideUntil);
                cwuDuration.textContent = remaining;
            }
        } else if (currentData.floorHeatingActive || currentData.state === 'heating_floor') {
            floorBtn.classList.add('active');
            if (overrideUntil) {
                const remaining = getTimeRemaining(overrideUntil);
                floorDuration.textContent = remaining;
            }
        }
    }
}

function getTimeRemaining(isoString) {
    const until = new Date(isoString);
    const now = new Date();
    const diffMs = until - now;
    if (diffMs <= 0) return '';

    const mins = Math.floor(diffMs / 60000);
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    const remainMins = mins % 60;
    return remainMins > 0 ? `${hours}h ${remainMins}m` : `${hours}h`;
}

async function setModeAuto() {
    // Always call force_auto - it cancels manual override AND floor boost
    await callService('cwu_controller', 'force_auto');
    showNotification('Switched to AUTO mode', 'success');
}

function openModeModal(type) {
    selectedModeType = type;
    selectedDuration = 3;
    selectedModeTab = 'duration';

    const modal = document.getElementById('mode-modal');
    const title = document.getElementById('mode-modal-title');
    const icon = document.getElementById('mode-modal-icon');
    const desc = document.getElementById('mode-modal-description');
    const slider = document.getElementById('duration-slider');
    const tabsCwu = document.getElementById('mode-tabs-cwu');
    const tabsFloor = document.getElementById('mode-tabs-floor');

    if (type === 'cwu') {
        title.textContent = 'Force CWU Heating';
        icon.innerHTML = '<span class="mdi mdi-water-boiler"></span>';
        icon.querySelector('.mdi').style.color = 'var(--accent-cyan)';
        desc.textContent = 'Force CWU heating for:';
        // Show CWU tabs (duration + heat-to)
        tabsCwu.style.display = 'flex';
        tabsFloor.style.display = 'none';
    } else {
        title.textContent = 'Floor Heating';
        icon.innerHTML = '<span class="mdi mdi-heating-coil"></span>';
        icon.querySelector('.mdi').style.color = 'var(--accent-orange)';
        desc.textContent = 'Force floor heating for:';
        // Show Floor tabs (duration + boost)
        tabsCwu.style.display = 'none';
        tabsFloor.style.display = 'flex';
    }

    // Reset to duration tab
    switchModeTab('duration');

    slider.value = selectedDuration;
    updateDurationDisplay();
    updatePresetButtons();
    updateBoostStatus();

    modal.classList.add('open');
}

function switchModeTab(tab) {
    selectedModeTab = tab;

    // CWU tabs
    const tabDurationCwu = document.getElementById('tab-duration-cwu');
    const tabHeatTo = document.getElementById('tab-heat-to');
    // Floor tabs
    const tabDurationFloor = document.getElementById('tab-duration-floor');
    const tabBoost = document.getElementById('tab-boost');
    const tabFloorTemp = document.getElementById('tab-floor-temp');
    // Panels
    const panelDuration = document.getElementById('panel-duration');
    const panelHeatTo = document.getElementById('panel-heat-to');
    const panelBoost = document.getElementById('panel-boost');
    const panelFloorTemp = document.getElementById('panel-floor-temp');
    const confirmBtn = document.getElementById('mode-confirm-btn');

    // Reset all tabs and panels
    [tabDurationCwu, tabHeatTo, tabDurationFloor, tabBoost, tabFloorTemp].forEach(t => t?.classList.remove('active'));
    [panelDuration, panelHeatTo, panelBoost, panelFloorTemp].forEach(p => { if(p) p.style.display = 'none'; });

    if (tab === 'duration') {
        if (selectedModeType === 'cwu') {
            tabDurationCwu?.classList.add('active');
        } else {
            tabDurationFloor?.classList.add('active');
        }
        panelDuration.style.display = 'block';
        confirmBtn.style.display = 'block';
        confirmBtn.innerHTML = '<span class="mdi mdi-check"></span> Confirm';
    } else if (tab === 'heat-to') {
        tabHeatTo?.classList.add('active');
        panelHeatTo.style.display = 'block';
        confirmBtn.style.display = 'block';
        confirmBtn.innerHTML = '<span class="mdi mdi-fire"></span> Start Heating';
    } else if (tab === 'boost') {
        tabBoost?.classList.add('active');
        panelBoost.style.display = 'block';
        // Hide the generic confirm button - boost has its own buttons
        confirmBtn.style.display = 'none';
        updateBoostStatus();
    } else if (tab === 'floor-temp') {
        tabFloorTemp?.classList.add('active');
        panelFloorTemp.style.display = 'block';
        // Hide the generic confirm button - floor-temp has its own button
        confirmBtn.style.display = 'none';
        updateFloorTempFromBsb();
    }
}

function updateDurationDisplay() {
    const slider = document.getElementById('duration-slider');
    const display = document.getElementById('duration-value');
    selectedDuration = parseFloat(slider.value);
    display.textContent = selectedDuration;
    updatePresetButtons();
}

function setDuration(hours) {
    selectedDuration = hours;
    document.getElementById('duration-slider').value = hours;
    document.getElementById('duration-value').textContent = hours;
    updatePresetButtons();
}

function updatePresetButtons() {
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.classList.remove('active');
        const btnHours = parseFloat(btn.textContent);
        if (btnHours === selectedDuration) {
            btn.classList.add('active');
        }
    });
}

async function confirmMode() {
    closeModal('mode-modal');

    if (selectedModeTab === 'heat-to' && selectedModeType === 'cwu') {
        // Heat-to mode
        const targetTemp = parseInt(document.getElementById('heat-to-temp').value);
        if (targetTemp < 36 || targetTemp > 55) {
            showNotification('Temperature must be between 36°C and 55°C', 'error');
            return;
        }
        try {
            await callService('cwu_controller', 'heat_to_temp', { target_temp: targetTemp });
            showNotification(`Heating CWU to ${targetTemp}°C`, 'success');
        } catch (error) {
            showNotification('Failed to start heat-to: ' + error.message, 'error');
        }
    } else {
        // Duration mode (force CWU or force floor)
        const durationMinutes = selectedDuration * 60;
        if (selectedModeType === 'cwu') {
            await callService('cwu_controller', 'force_cwu', { duration: durationMinutes });
        } else {
            await callService('cwu_controller', 'force_floor', { duration: durationMinutes });
        }
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
    if (entityId) await callService('button', 'press', { entity_id: entityId });
}

/**
 * Heat-to temperature functions
 */
function setHeatToTemp(temp) {
    document.getElementById('heat-to-temp').value = temp;
    // Update active preset button
    document.querySelectorAll('.heat-to-presets .preset-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.textContent.includes(temp + '°C')) {
            btn.classList.add('active');
        }
    });
}

function updateHeatToProgress() {
    const attrs = currentData.attributes || {};
    const heatToActive = attrs.manual_heat_to_active;
    const heatToTarget = attrs.manual_heat_to_target;
    const cwuTemp = currentData.cwuTemp;

    const progressContainer = document.getElementById('heat-to-progress');
    const progressFill = document.getElementById('heat-to-progress-fill');
    const progressText = document.getElementById('heat-to-progress-text');

    if (heatToActive && heatToTarget) {
        progressContainer.style.display = 'block';

        const startTemp = Math.max(35, cwuTemp - 10); // Approximate start
        const progress = Math.min(100, Math.max(0, ((cwuTemp - startTemp) / (heatToTarget - startTemp)) * 100));
        progressFill.style.width = progress + '%';
        progressText.textContent = `${cwuTemp?.toFixed(1) || '--'}°C / ${heatToTarget}°C`;
    } else {
        progressContainer.style.display = 'none';
    }
}

/**
 * Floor Boost functions
 */
let selectedBoostDuration = 2;

function updateBoostDurationDisplay() {
    const slider = document.getElementById('boost-duration-slider');
    const display = document.getElementById('boost-duration-value');
    selectedBoostDuration = parseInt(slider.value);
    display.textContent = selectedBoostDuration;
    updateBoostPresetButtons();
}

function setBoostDuration(hours) {
    selectedBoostDuration = hours;
    document.getElementById('boost-duration-slider').value = hours;
    document.getElementById('boost-duration-value').textContent = hours;
    updateBoostPresetButtons();
}

function updateBoostPresetButtons() {
    document.querySelectorAll('.boost-presets .preset-btn').forEach(btn => {
        btn.classList.remove('active');
        const btnHours = parseInt(btn.textContent);
        if (btnHours === selectedBoostDuration) {
            btn.classList.add('active');
        }
    });
}

async function confirmBoostDuration() {
    closeModal('mode-modal');
    try {
        await callService('cwu_controller', 'floor_boost', { hours: selectedBoostDuration });
        showNotification(`Floor boost started for ${selectedBoostDuration}h (28°C)`, 'success');
    } catch (error) {
        showNotification('Failed to start floor boost: ' + error.message, 'error');
    }
}

async function confirmBoostSession() {
    closeModal('mode-modal');
    try {
        await callService('cwu_controller', 'floor_boost_session');
        showNotification('Floor boost started until session ends (28°C)', 'success');
    } catch (error) {
        showNotification('Failed to start floor boost: ' + error.message, 'error');
    }
}

async function cancelBoost() {
    try {
        await callService('cwu_controller', 'floor_boost_cancel');
        showNotification('Floor boost cancelled', 'info');
        updateBoostStatus();
    } catch (error) {
        showNotification('Failed to cancel boost: ' + error.message, 'error');
    }
}

function updateBoostStatus() {
    const attrs = currentData.attributes || {};
    const boostActive = attrs.floor_boost_active;
    const boostSession = attrs.floor_boost_session;
    const boostUntil = attrs.floor_boost_until;

    const statusEl = document.getElementById('boost-status');
    const statusText = document.getElementById('boost-status-text');
    const sessionBtn = document.getElementById('boost-session-btn');
    const durationSlider = document.querySelector('.boost-option');

    if (boostActive) {
        statusEl.style.display = 'flex';
        if (boostSession) {
            statusText.textContent = 'Boost active (until session ends)';
        } else if (boostUntil) {
            const until = new Date(boostUntil);
            const remaining = Math.max(0, Math.round((until - new Date()) / 60000));
            const hours = Math.floor(remaining / 60);
            const mins = remaining % 60;
            statusText.textContent = `Boost active (${hours}h ${mins}m remaining)`;
        } else {
            statusText.textContent = 'Boost active';
        }
        // Show cancel button, hide start controls
        sessionBtn.textContent = 'Cancel Boost';
        sessionBtn.classList.add('btn-cancel-boost');
        sessionBtn.onclick = cancelBoost;
        if (durationSlider) durationSlider.style.display = 'none';
        document.querySelector('.boost-divider').style.display = 'none';
    } else {
        statusEl.style.display = 'none';
        // Show start controls
        sessionBtn.innerHTML = '<span class="mdi mdi-timer-sand"></span> Until Session Ends';
        sessionBtn.classList.remove('btn-cancel-boost');
        sessionBtn.onclick = confirmBoostSession;
        if (durationSlider) durationSlider.style.display = 'flex';
        document.querySelector('.boost-divider').style.display = 'flex';
    }
}

/**
 * Floor Temperature Setting functions
 */
let selectedFloorTemp = 21;

function updateFloorTempDisplay() {
    const slider = document.getElementById('floor-temp-slider');
    const display = document.getElementById('floor-temp-value');
    selectedFloorTemp = parseFloat(slider.value);
    display.textContent = selectedFloorTemp;
    updateFloorTempPresetButtons();
}

function setFloorTemp(temp) {
    selectedFloorTemp = temp;
    document.getElementById('floor-temp-slider').value = temp;
    document.getElementById('floor-temp-value').textContent = temp;
    updateFloorTempPresetButtons();
}

function updateFloorTempPresetButtons() {
    document.querySelectorAll('.floor-temp-presets .preset-btn').forEach(btn => {
        btn.classList.remove('active');
        const btnTemp = parseFloat(btn.textContent);
        if (btnTemp === selectedFloorTemp) {
            btn.classList.add('active');
        }
    });
}

function updateFloorTempFromBsb() {
    // Get current floor setpoint from BSB-LAN data (param 710)
    const attrs = currentData.attributes || {};
    const bsbLan = attrs.bsb_lan || {};
    const floorSetpoint = bsbLan.floor_comfort_setpoint;
    if (floorSetpoint !== undefined && floorSetpoint !== null) {
        const currentTemp = parseFloat(floorSetpoint);
        document.getElementById('floor-temp-current-value').textContent = currentTemp.toFixed(1);
        // Set slider to current value
        setFloorTemp(currentTemp);
    } else {
        document.getElementById('floor-temp-current-value').textContent = '--';
    }
}

async function confirmFloorTemp() {
    closeModal('mode-modal');
    try {
        await callService('cwu_controller', 'floor_set_temperature', { temperature: selectedFloorTemp });
        showNotification(`Floor temperature set to ${selectedFloorTemp}°C`, 'success');
    } catch (error) {
        showNotification('Failed to set floor temperature: ' + error.message, 'error');
    }
}

/**
 * Dismiss alert
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
        <span class="notification-icon mdi ${type === 'error' ? 'mdi-alert-circle' : type === 'success' ? 'mdi-check-circle' : 'mdi-information'}"></span>
        <span class="notification-message">${message}</span>
        <button class="notification-close" onclick="this.parentElement.remove()"><span class="mdi mdi-close"></span></button>
    `;
    container.appendChild(notification);
    setTimeout(() => notification.classList.add('show'), 10);
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

/**
 * Update last update time
 */
function updateLastUpdateTime() {
    const el = document.getElementById('last-update');
    if (el) el.textContent = new Date().toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/**
 * BSB-LAN Display Functions - Uses coordinator sensor entities (updated every 60s)
 * No direct API calls - data comes from refreshData() via HA sensor entities
 */
function updateBsbLanDisplay(bsbData) {
    const contentEl = document.getElementById('bsb-lan-content');
    const statusEl = document.getElementById('bsb-lan-status');
    if (!contentEl) return;

    // Use cached data if not provided
    const data = bsbData || currentData.bsbLan;

    // Handle unavailable or missing data
    if (!data || !data.available) {
        const reason = data?.control_source === 'ha_cloud' ? 'Using HA Cloud fallback' : 'BSB-LAN unavailable';
        contentEl.innerHTML = `
            <div class="bsb-error">
                <span class="mdi mdi-lan-disconnect"></span>
                <span>${reason}</span>
            </div>
        `;
        if (statusEl) {
            statusEl.innerHTML = '<span class="mdi mdi-alert-circle" style="color: var(--accent-orange);"></span>';
        }
        return;
    }

    // Parse values from sensor data
    const dhwStatus = data.dhw_status || '---';
    const hpStatus = data.hp_status || '---';
    const hc1Status = data.hc1_status || '---';
    const cwuMode = data.cwu_mode || '---';
    const cwuModeOn = data.cwu_mode_on || false;
    const floorMode = data.floor_mode || '---';
    const floorModeOn = data.floor_mode_on || false;
    const flowTemp = data.flow_temp || 0;
    const returnTemp = data.return_temp || 0;
    const cwuTemp = data.cwu_temp || 0;
    const outsideTemp = data.outside_temp || 0;
    const deltaT = data.delta_t !== null && !isNaN(data.delta_t) ? data.delta_t : (flowTemp - returnTemp);
    const controlSource = data.control_source || 'unknown';

    // Delta T interpretation
    let deltaTClass = 'normal';
    let deltaTDesc = '';
    if (deltaT < 0) {
        deltaTClass = 'bad';
        deltaTDesc = 'Reversed';
    } else if (deltaT >= 3 && deltaT <= 5) {
        deltaTClass = 'good';
        deltaTDesc = 'Normal';
    } else if (deltaT > 0.5 && deltaT < 3) {
        deltaTClass = 'warning';
        deltaTDesc = 'Weak';
    } else if (deltaT <= 0.5) {
        deltaTClass = 'bad';
        deltaTDesc = 'No flow';
    } else if (deltaT > 5) {
        deltaTClass = 'high';
        deltaTDesc = 'High';
    }

    // Control source indicator
    const sourceIcon = controlSource === 'bsb_lan' ? 'mdi-lan-connect' : 'mdi-cloud';
    const sourceLabel = controlSource === 'bsb_lan' ? 'BSB-LAN' : 'HA Cloud';

    // Get additional controller data from attributes
    const attrs = currentData.attributes || {};
    const hpReady = attrs.hp_ready !== false;
    const hpReadyReason = attrs.hp_ready_reason || 'OK';
    const holdTimeRemaining = attrs.hold_time_remaining || 0;
    const switchBlockedReason = attrs.switch_blocked_reason || '';
    const maxTempAchieved = attrs.max_temp_achieved;
    const electricFallbackCount = attrs.electric_fallback_count || 0;
    const isNightFloorWindow = attrs.is_night_floor_window || false;
    const operatingMode = attrs.operating_mode || 'broken_heater';

    // HP ready status display
    const hpReadyIcon = hpReady ? 'mdi-check-circle' : 'mdi-timer-sand';
    const hpReadyClass = hpReady ? 'ready' : 'waiting';
    const hpReadyText = hpReady ? 'Ready' : hpReadyReason;

    // Hold time / switch blocked display
    let holdDisplay = '';
    if (holdTimeRemaining > 0) {
        holdDisplay = `<div class="bsb-hold-time"><span class="mdi mdi-timer"></span> Hold: ${Math.round(holdTimeRemaining)}min</div>`;
    } else if (switchBlockedReason) {
        holdDisplay = `<div class="bsb-hold-time blocked"><span class="mdi mdi-block-helper"></span> ${switchBlockedReason}</div>`;
    }

    // Max temp achieved display
    let maxTempDisplay = '';
    if (maxTempAchieved !== null && maxTempAchieved !== undefined) {
        maxTempDisplay = `<div class="bsb-max-temp"><span class="mdi mdi-thermometer-alert"></span> Max: ${maxTempAchieved.toFixed(1)}°C (electric x${electricFallbackCount})</div>`;
    }

    // Night floor window display
    let nightWindowDisplay = '';
    if (operatingMode === 'broken_heater' && isNightFloorWindow) {
        nightWindowDisplay = `<div class="bsb-night-window"><span class="mdi mdi-weather-night"></span> Floor window (03:00-06:00)</div>`;
    }

    contentEl.innerHTML = `
        <div class="bsb-modes-row">
            <div class="bsb-mode-badge ${cwuModeOn ? 'on' : 'off'}">
                <span class="mdi mdi-water-boiler"></span>
                <span class="bsb-mode-label">CWU</span>
                <span class="bsb-mode-state">${cwuModeOn ? 'ON' : 'OFF'}</span>
                <span class="bsb-mode-detail">${cwuMode}</span>
            </div>
            <div class="bsb-mode-badge ${floorModeOn ? 'on' : 'off'}">
                <span class="mdi mdi-heating-coil"></span>
                <span class="bsb-mode-label">Floor</span>
                <span class="bsb-mode-state">${floorModeOn ? 'ON' : 'OFF'}</span>
                <span class="bsb-mode-detail">${floorMode}</span>
            </div>
        </div>
        <div class="bsb-status-row">
            <div class="bsb-raw-statuses">
                <div class="bsb-raw-status">
                    <span class="bsb-raw-label">DHW:</span>
                    <span class="bsb-raw-value">${dhwStatus}</span>
                </div>
                <div class="bsb-raw-status">
                    <span class="bsb-raw-label">HP:</span>
                    <span class="bsb-raw-value">${hpStatus}</span>
                </div>
                <div class="bsb-raw-status">
                    <span class="bsb-raw-label">HC1:</span>
                    <span class="bsb-raw-value">${hc1Status}</span>
                </div>
            </div>
            <div class="bsb-outside-temp">
                <span class="mdi mdi-thermometer"></span>
                <span>${outsideTemp.toFixed(1)}°C</span>
            </div>
        </div>
        <div class="bsb-temps-grid">
            <div class="bsb-temp-item">
                <span class="bsb-temp-label">CWU (BSB)</span>
                <span class="bsb-temp-value">${cwuTemp.toFixed(1)}°C</span>
            </div>
            <div class="bsb-temp-item flow">
                <span class="bsb-temp-label">Flow</span>
                <span class="bsb-temp-value">${flowTemp.toFixed(1)}°C</span>
            </div>
            <div class="bsb-temp-item return">
                <span class="bsb-temp-label">Return</span>
                <span class="bsb-temp-value">${returnTemp.toFixed(1)}°C</span>
            </div>
            <div class="bsb-temp-item delta ${deltaTClass}">
                <span class="bsb-temp-label">ΔT</span>
                <span class="bsb-temp-value">${deltaT >= 0 ? '+' : ''}${deltaT.toFixed(1)}°C</span>
                <span class="bsb-temp-desc">${deltaTDesc}</span>
            </div>
        </div>
        ${operatingMode === 'broken_heater' ? `
        <div class="bsb-controller-status">
            <div class="bsb-hp-ready ${hpReadyClass}">
                <span class="mdi ${hpReadyIcon}"></span>
                <span>HP: ${hpReadyText}</span>
            </div>
            ${holdDisplay}
            ${maxTempDisplay}
            ${nightWindowDisplay}
        </div>
        ` : ''}
        <div class="bsb-control-source">
            <span class="mdi ${sourceIcon}"></span>
            <span>Control: ${sourceLabel}</span>
        </div>
    `;

    // Update status indicator
    if (statusEl) {
        statusEl.innerHTML = '<span class="mdi mdi-check-circle" style="color: var(--accent-green);"></span>';
    }
}

/**
 * Initialize quick power sparkline chart
 */
function initQuickPowerChart() {
    const ctx = document.getElementById('quickPowerChart');
    if (!ctx) return;

    quickPowerChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
            datasets: [{
                data: [],
                borderColor: '#fc8181',
                backgroundColor: 'rgba(252, 129, 129, 0.3)',
                borderWidth: 2,
                tension: 0.3,
                fill: true,
                pointRadius: 0,
                pointHoverRadius: 0,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            scales: {
                x: {
                    type: 'time',
                    display: false,
                },
                y: {
                    display: false,
                    suggestedMin: 0,
                    suggestedMax: 2000
                }
            },
            interaction: { mode: 'none' },
            animation: { duration: 0 }
        }
    });
}

/**
 * Update quick power sparkline chart with 1h data
 */
async function updateQuickPowerChart() {
    if (!quickPowerChart) return;

    const history = await fetchHistory(EXTERNAL_ENTITIES.power, 1);

    const chartData = history
        .filter(item => item.state !== 'unavailable' && item.state !== 'unknown')
        .map(item => ({
            x: new Date(item.last_changed || item.last_updated),
            y: parseFloat(item.state) || 0
        }))
        .filter(item => !isNaN(item.y));

    if (chartData.length > 0) {
        // Auto-scale Y axis based on data
        const maxPower = Math.max(...chartData.map(d => d.y));
        quickPowerChart.options.scales.y.suggestedMax = Math.max(500, maxPower * 1.1);
    }

    quickPowerChart.data.datasets[0].data = chartData;
    quickPowerChart.update('none');
}

/**
 * Update quick stats widgets (Power, CWU Temp + State)
 */
function updateQuickStats() {
    // Update Power
    const quickPowerEl = document.getElementById('quick-power');
    if (quickPowerEl) {
        const power = currentData.power || 0;
        quickPowerEl.textContent = Math.round(power);

        // Color based on power level
        const powerWidget = quickPowerEl.closest('.quick-widget');
        powerWidget.classList.remove('idle', 'active', 'high');
        if (power < 50) {
            powerWidget.classList.add('idle');
        } else if (power < 1000) {
            powerWidget.classList.add('active');
        } else {
            powerWidget.classList.add('high');
        }
    }

    // Update CWU Temp
    const quickTempEl = document.getElementById('quick-cwu-temp');
    if (quickTempEl) {
        const temp = currentData.cwuTemp;
        quickTempEl.textContent = temp !== undefined ? temp.toFixed(1) : '--';
    }

    // Update State Badge
    const state = currentData.state || 'unknown';
    const quickStateIcon = document.getElementById('quick-state-icon');
    const quickStateName = document.getElementById('quick-state-name');
    const quickStateBadge = document.getElementById('quick-state-badge');
    const quickTempWidget = document.getElementById('quick-temp-widget');

    if (quickStateIcon && quickStateName && quickStateBadge) {
        const iconClass = STATE_ICONS[state] || 'mdi-help-circle';
        quickStateIcon.className = `mdi ${iconClass}`;

        // Format state name
        const stateName = state.replace(/_/g, ' ');
        quickStateName.textContent = stateName.charAt(0).toUpperCase() + stateName.slice(1);

        // Apply state class for coloring
        quickStateBadge.className = 'quick-state-badge';
        quickTempWidget.className = 'quick-widget temp-widget';

        if (state.includes('cwu') || state.includes('heating_cwu')) {
            quickStateBadge.classList.add('state-cwu');
            quickTempWidget.classList.add('state-cwu');
        } else if (state.includes('floor')) {
            quickStateBadge.classList.add('state-floor');
            quickTempWidget.classList.add('state-floor');
        } else if (state.includes('emergency')) {
            quickStateBadge.classList.add('state-emergency');
            quickTempWidget.classList.add('state-emergency');
        } else if (state.includes('pause')) {
            quickStateBadge.classList.add('state-pause');
            quickTempWidget.classList.add('state-pause');
        } else if (state.includes('safe_mode')) {
            quickStateBadge.classList.add('state-safe');
            quickTempWidget.classList.add('state-safe');
        }
    }

    // Update temp change (only when CWU is heating)
    const quickTempChange = document.getElementById('quick-temp-change');
    if (quickTempChange) {
        const attrs = currentData.attributes || {};
        const sessionStartTemp = attrs.cwu_session_start_temp;
        const isHeating = currentData.cwuHeatingActive;

        if (isHeating && sessionStartTemp !== undefined && currentData.cwuTemp !== undefined) {
            const change = currentData.cwuTemp - sessionStartTemp;
            quickTempChange.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(1)}°C`;
            quickTempChange.style.color = change >= 0 ? '#68d391' : '#fc8181';
            quickTempChange.style.display = 'inline';
        } else {
            quickTempChange.style.display = 'none';
        }
    }
}

/**
 * System Visualization Update Functions
 * Updates the holographic heat pump system visualization (both mobile and desktop versions)
 */
function updateSystemVisualization() {
    const vizCards = document.querySelectorAll('#system-viz-card, #system-viz-card-desktop');
    if (vizCards.length === 0) return;

    const state = currentData.state || 'idle';
    const bsb = currentData.bsbLan || {};
    const power = currentData.power || 0;
    const attrs = currentData.attributes || {};

    // Determine states
    const isFloorHeating = state.includes('floor') || state === 'heating_floor';
    const isIdle = state === 'idle';
    const isDefrost = (bsb.hp_status || '').toLowerCase().includes('defrost');

    // Apply classes to all viz cards
    vizCards.forEach(vizCard => {
        // Toggle tank/floor view based on current heating state
        vizCard.classList.toggle('show-floor', isFloorHeating);
        // Toggle defrost mode
        vizCard.classList.toggle('defrost', isDefrost);
        // Toggle stopped state (no animations when idle and low power)
        vizCard.classList.toggle('stopped', isIdle && power < 50);
    });

    // Update power display and fan speed
    updateVizPower(power);

    // Update temperatures
    const flowTemp = bsb.flow_temp || 0;
    const returnTemp = bsb.return_temp || 0;
    const deltaT = bsb.delta_t !== null && !isNaN(bsb.delta_t) ? bsb.delta_t : (flowTemp - returnTemp);
    const cwuTemp = currentData.cwuTemp || bsb.cwu_temp || 0;
    const targetTemp = currentData.cwuTargetTemp || attrs.cwu_target_temp;

    // Format temperature with comma (Polish format)
    const formatTemp = (temp) => temp ? temp.toFixed(1).replace('.', ',') + '°' : '--°';

    // Update all elements by class (works for both mobile and desktop)
    document.querySelectorAll('.viz-cwu-val, #viz-cwu-temp, .viz-cwu-temp-desktop').forEach(el => {
        el.textContent = formatTemp(cwuTemp);
    });

    document.querySelectorAll('.viz-target-val, #viz-target-temp, .viz-target-temp-desktop').forEach(el => {
        el.textContent = targetTemp ? Math.round(targetTemp) + '°C' : '--°C';
    });

    document.querySelectorAll('.viz-flow-val, #viz-flow-temp-cwu, #viz-flow-temp-floor, .viz-flow-temp-cwu-desktop, .viz-flow-temp-floor-desktop').forEach(el => {
        el.textContent = formatTemp(flowTemp);
    });

    document.querySelectorAll('.viz-return-val, #viz-return-temp-cwu, #viz-return-temp-floor, .viz-return-temp-cwu-desktop, .viz-return-temp-floor-desktop').forEach(el => {
        el.textContent = formatTemp(returnTemp);
    });

    document.querySelectorAll('.viz-delta-val, #viz-delta-cwu, #viz-delta-floor, .viz-delta-cwu-desktop, .viz-delta-floor-desktop').forEach(el => {
        el.textContent = (deltaT >= 0 ? '+' : '') + deltaT.toFixed(1) + '°C';
    });

    // Update status texts
    document.querySelectorAll('.viz-dhw-val, #viz-dhw-status, .viz-dhw-status-desktop').forEach(el => {
        el.textContent = bsb.dhw_status || '---';
    });

    document.querySelectorAll('.viz-hc1-val, #viz-hc1-status, .viz-hc1-status-desktop').forEach(el => {
        el.textContent = bsb.hc1_status || '---';
    });

    document.querySelectorAll('.viz-hp-val, #viz-hp-status, .viz-hp-status-desktop').forEach(el => {
        el.textContent = bsb.hp_status || '---';
    });

    // Update state badge (reuse 'state' from above)
    const stateBadge = document.getElementById('viz-state-badge');
    if (stateBadge) {
        stateBadge.textContent = state.replace(/_/g, ' ').toUpperCase();
        stateBadge.className = 'badge' + (state.includes('cwu') ? ' badge-danger' : state.includes('floor') ? ' badge-success' : '');
    }
}

/**
 * Update visualization power display and fan speed
 */
function updateVizPower(watts) {
    const vizCards = document.querySelectorAll('#system-viz-card, #system-viz-card-desktop');

    // Format power text
    let powerText, unitText;
    if (watts >= 1000) {
        powerText = (watts / 1000).toFixed(1).replace('.', ',');
        unitText = 'kW';
    } else if (watts > 0) {
        powerText = Math.round(watts).toString();
        unitText = 'W';
    } else {
        powerText = '--';
        unitText = 'W';
    }

    // Update all power displays
    document.querySelectorAll('.viz-power-val, #viz-power-value, .viz-power-value-desktop').forEach(el => {
        el.textContent = powerText;
    });
    document.querySelectorAll('.viz-power-un, #viz-power-unit, .viz-power-unit-desktop').forEach(el => {
        el.textContent = unitText;
    });

    // Calculate fan speed based on power
    let fanSpeed;
    if (watts === 0 || watts < 10) {
        fanSpeed = '0s';
    } else {
        // Speed formula: faster rotation with higher power
        // 100W = 8s, 500W = 4s, 1000W = 2s, 2000W = 1s, 3000W = 0.6s
        fanSpeed = Math.max(0.5, 2000 / watts) + 's';
    }

    // Apply to all cards and fans
    vizCards.forEach(card => {
        card.style.setProperty('--viz-fan-speed', fanSpeed);
    });

    document.querySelectorAll('#viz-fan, #viz-fan-d').forEach(fan => {
        fan.classList.toggle('off', watts < 10);
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', init);

// Close modals on escape or outside click
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open'));
    }
});

document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', e => {
        if (e.target === modal) modal.classList.remove('open');
    });
});
