/* ==========================================================================
   DASHBOARD MAIN CORE APP (JS)
   ==========================================================================
   Project:  Vision-Based Autonomous Robotic Arm
   File:     app.js
   Location: dashboard/frontend/js/

   PURPOSE:
     Handles sidebar tab navigation, WebSocket real-time connection management,
     reconnection logic, activity logging, and UI status pill updates.
   ========================================================================== */

const App = {
  ws: null,
  wsUrl: `ws://${window.location.host}/ws`,
  reconnectInterval: 3000,
  
  init() {
    this.setupNavigation();
    this.connectWebSocket();
  },

  /* Sidebar Tab Switching */
  setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const panels = document.querySelectorAll('.content-panel');
    const pageTitle = document.getElementById('page-title');

    const titles = {
      'panel-control': 'Robot Servo Control & Assembly Helper',
      'panel-digital-twin': '3D Digital Twin Simulation (Baby ROS / URDF)',
      'panel-journal': 'Robotic Arm Project Journal & Log Archive',
      'panel-camera': 'Live Dual-Camera Feeds',
      'panel-perception': 'OpenCV Perception & Coordinate Mapping',
      'panel-teleop': 'PS5 Controller Teleoperation & IK',
      'panel-dataset': 'Demonstration Dataset Management',
      'panel-autonomous': 'ONNX Autonomous Policy — Pick & Place'
    };

    navItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPanelId = item.getAttribute('data-panel');

        // Update active nav button
        navItems.forEach(n => n.classList.remove('active'));
        item.classList.add('active');

        // Update active panel
        panels.forEach(p => {
          if (p.id === targetPanelId) {
            p.classList.add('active');
          } else {
            p.classList.remove('active');
          }
        });

        // Update title
        if (pageTitle && titles[targetPanelId]) {
          pageTitle.textContent = titles[targetPanelId];
        }
      });
    });
  },

  /* WebSocket Management */
  connectWebSocket() {
    try {
      this.ws = new WebSocket(this.wsUrl);

      this.ws.onopen = () => {
        this.log('WebSocket connected to backend.');
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'status') {
            this.handleStatusUpdate(msg.data);
          } else if (msg.type === 'onnx_status') {
            if (window.OnnxPanel) {
              window.OnnxPanel.handleStatus(msg.data);
            }
          }
        } catch (err) {
          console.warn('Failed to parse WebSocket JSON:', err);
        }
      };

      this.ws.onclose = () => {
        this.updateStatusPill(false, 'Disconnected (Reconnecting...)');
        setTimeout(() => this.connectWebSocket(), this.reconnectInterval);
      };

      this.ws.onerror = (err) => {
        console.error('WebSocket error:', err);
      };

    } catch (e) {
      console.warn('WebSocket connection failed, operating in offline UI mode:', e);
    }
  },

  /* Send JSON payload over WebSocket */
  sendWS(type, payload = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, ...payload }));
    } else {
      console.log(`[Offline Mode WS Send] ${type}:`, payload);
    }
  },

  /* Update Header Status Pill */
  handleStatusUpdate(data) {
    const statusPill = document.getElementById('statusPill');
    const statusText = document.getElementById('statusText');

    if (data.is_estop) {
      statusPill.className = 'status-pill estop';
      statusText.textContent = 'EMERGENCY STOP ACTIVE';
      
      const btnResetEstop = document.getElementById('btnResetEstop');
      if (btnResetEstop) btnResetEstop.style.display = 'block';

    } else if (data.is_connected) {
      statusPill.className = 'status-pill connected';
      statusText.textContent = `Connected: ${data.port} (${data.baudrate} Baud)`;
      
      const btnResetEstop = document.getElementById('btnResetEstop');
      if (btnResetEstop) btnResetEstop.style.display = 'none';

    } else {
      statusPill.className = 'status-pill';
      statusText.textContent = 'Offline / Disconnected';

      const btnResetEstop = document.getElementById('btnResetEstop');
      if (btnResetEstop) btnResetEstop.style.display = 'none';
    }

    // Update Arduino CLI status badge (Decision #15)
    const cliBadge = document.getElementById('cliStatusBadge');
    if (cliBadge) {
      if (data.has_arduino_cli) {
        cliBadge.style.borderColor = 'var(--accent-success)';
        cliBadge.style.color = 'var(--accent-success)';
        cliBadge.textContent = `Arduino CLI: Installed (${data.arduino_cli_info})`;
      } else {
        cliBadge.style.borderColor = 'var(--border-subtle)';
        cliBadge.style.color = 'var(--text-muted)';
        cliBadge.textContent = `Arduino CLI: Not Installed (Falling back to PySerial)`;
      }
    }

    // Update Servo Control Sliders live from backend WebSocket telemetry
    if (window.ServoPanel && data.angles) {
      window.ServoPanel.updateSlidersFromBackend(data.angles);
    }

    // Update Digital Twin 3D Viewport Telemetry Overlay
    if (data.angles) {
      for (let i = 0; i < Math.min(data.angles.length, 6); i++) {
        const el = document.getElementById(`dtVal${i}`);
        if (el) el.textContent = `${data.angles[i]}°`;
      }
    }
  },

  updateStatusPill(isConnected, text) {
    const statusPill = document.getElementById('statusPill');
    const statusText = document.getElementById('statusText');
    if (statusPill && statusText) {
      statusPill.className = isConnected ? 'status-pill connected' : 'status-pill';
      statusText.textContent = text;
    }
  },

  /* Activity Logging Box */
  log(message) {
    const logBox = document.getElementById('logBox');
    if (!logBox) return;

    const entry = document.createElement('div');
    entry.className = 'log-entry';

    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];

    entry.innerHTML = `<span class="log-time">[${timeStr}]</span> ${message}`;
    logBox.appendChild(entry);
    logBox.scrollTop = logBox.scrollHeight;
  }
};

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
