/*
 * PitPat Treadmill card. Served and registered by the integration itself, so it
 * shows up in the dashboard card picker as "PitPat Treadmill" with no resource
 * setup. It is a thin wrapper that renders a layout of Home Assistant's own cards.
 *
 *   type: custom:pitpat-treadmill-card
 *   prefix: pitpat_treadmill   # optional: entity id prefix, if you renamed the device
 */
(() => {
  const entityId = (prefix, domain, name) => `${domain}.${prefix}_${name}`;

  const buildConfig = (prefix) => {
    const e = (domain, name) => entityId(prefix, domain, name);
    const state = e("sensor", "state");
    return {
      type: "vertical-stack",
      cards: [
        {
          type: "grid",
          columns: 2,
          square: false,
          cards: [
            {
              type: "gauge",
              entity: e("sensor", "speed"),
              name: "Speed",
              unit: "km/h",
              min: 0,
              max: 6,
              needle: true,
              segments: [
                { from: 0, color: "#43a047" },
                { from: 3.5, color: "#fb8c00" },
                { from: 5, color: "#e53935" },
              ],
            },
            {
              type: "vertical-stack",
              cards: [
                { type: "tile", entity: e("switch", "bluetooth_connection"), name: "Connection", icon: "mdi:bluetooth", vertical: false },
                { type: "tile", entity: state, name: "State", icon: "mdi:run", vertical: false },
                { type: "tile", entity: e("sensor", "workout_time"), name: "Time", vertical: false },
              ],
            },
          ],
        },
        {
          type: "grid",
          columns: 3,
          square: false,
          cards: [
            { type: "tile", entity: e("sensor", "distance"), name: "Distance", vertical: true },
            { type: "tile", entity: e("sensor", "calories"), name: "Calories", vertical: true },
            { type: "tile", entity: e("sensor", "target_speed"), name: "Target", vertical: true },
          ],
        },
        {
          type: "entities",
          show_header_toggle: false,
          entities: [{ entity: e("number", "speed_setting"), name: "Speed setting" }],
        },
        {
          type: "grid",
          columns: 4,
          square: false,
          cards: [
            { type: "tile", entity: e("button", "slower"), name: "Slower", icon: "mdi:minus", vertical: true },
            {
              type: "conditional",
              conditions: [{ condition: "state", entity: state, state: "running" }],
              card: {
                type: "tile", entity: e("button", "pause"), name: "Pause",
                icon: "mdi:pause", color: "orange", vertical: true,
              },
            },
            {
              type: "conditional",
              conditions: [{ condition: "state", entity: state, state_not: "running" }],
              card: {
                type: "tile", entity: e("button", "start"), name: "Start",
                icon: "mdi:play", color: "green", vertical: true,
              },
            },
            { type: "tile", entity: e("button", "faster"), name: "Faster", icon: "mdi:plus", vertical: true },
            {
              type: "tile", entity: e("button", "stop"), name: "Stop",
              icon: "mdi:stop", color: "red", vertical: true,
            },
          ],
        },
        {
          type: "history-graph",
          hours_to_show: 1,
          entities: [
            { entity: e("sensor", "speed"), name: "Speed" },
            { entity: e("sensor", "target_speed"), name: "Target" },
          ],
        },
      ],
    };
  };

  class PitPatTreadmillCard extends HTMLElement {
    static getStubConfig() {
      return {};
    }

    setConfig(config) {
      this._config = { prefix: "pitpat_treadmill", ...config };
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._card) return;
      try {
        this._card.hass = hass;
      } catch (err) {
        // A transient failure in a child card must not take the whole card down.
        console.warn("pitpat-treadmill-card: hass update failed, rebuilding", err);
        this._scheduleRetry();
      }
    }

    connectedCallback() {
      // Rebuild after Home Assistant reloads the dashboard (edit mode, resources).
      this._onRebuild = () => this._render();
      window.addEventListener("ll-rebuild", this._onRebuild);
      if (this._config && !this._card) this._render();
    }

    disconnectedCallback() {
      window.removeEventListener("ll-rebuild", this._onRebuild);
      clearTimeout(this._retry);
    }

    getCardSize() {
      return 10;
    }

    _scheduleRetry() {
      clearTimeout(this._retry);
      this._retry = setTimeout(() => this._render(), 1000);
    }

    async _helpers() {
      // The card script can load before the dashboard has defined its helpers.
      for (let i = 0; i < 100; i++) {
        if (window.loadCardHelpers) return window.loadCardHelpers();
        await new Promise((r) => setTimeout(r, 100));
      }
      throw new Error("Home Assistant card helpers are not available");
    }

    async _render() {
      const token = (this._token = Symbol());
      try {
        const helpers = await this._helpers();
        if (token !== this._token) return; // a newer setConfig superseded this one
        const card = helpers.createCardElement(buildConfig(this._config.prefix));
        if (this._hass) card.hass = this._hass;
        this._card = card;
        this.replaceChildren(card);
      } catch (err) {
        if (token !== this._token) return;
        console.error("pitpat-treadmill-card: render failed", err);
        this._card = null;
        const msg = document.createElement("ha-alert");
        msg.setAttribute("alert-type", "error");
        msg.textContent = `PitPat card failed to render: ${err && err.message ? err.message : err}`;
        this.replaceChildren(msg);
        this._scheduleRetry();
      }
    }
  }

  if (!customElements.get("pitpat-treadmill-card")) {
    customElements.define("pitpat-treadmill-card", PitPatTreadmillCard);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "pitpat-treadmill-card",
      name: "PitPat Treadmill",
      description: "Speedometer, totals, speed slider and start / pause / stop controls.",
    });
  }
})();
