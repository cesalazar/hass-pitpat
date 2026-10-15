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
      if (this._card) this._card.hass = hass;
    }

    getCardSize() {
      return 10;
    }

    async _render() {
      const token = (this._token = Symbol());
      const helpers = await window.loadCardHelpers();
      if (token !== this._token) return; // a newer setConfig superseded this one
      const card = helpers.createCardElement(buildConfig(this._config.prefix));
      if (this._hass) card.hass = this._hass;
      this._card = card;
      this.replaceChildren(card);
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
