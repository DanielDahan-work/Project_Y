(() => {
    "use strict";

    const clock = document.querySelector("[data-clock]");
    const clockDate = document.querySelector("[data-clock-date]");
    if (clock) {
        const options = { timeZone: clock.dataset.timezone };
        const timeFormat = new Intl.DateTimeFormat("en-GB", {
            ...options, hour: "2-digit", minute: "2-digit", second: "2-digit",
            hourCycle: "h23",
        });
        const dateFormat = new Intl.DateTimeFormat("en-GB", {
            ...options, day: "numeric", month: "short", year: "numeric",
        });
        const updateClock = () => {
            const now = new Date();
            clock.textContent = timeFormat.format(now);
            clock.dateTime = now.toISOString();
            if (clockDate) clockDate.textContent = dateFormat.format(now);
        };
        updateClock();
        window.setInterval(updateClock, 1000);
    }

    const weather = document.querySelector("[data-weather]");
    const status = document.querySelector("[data-weather-status]");
    if (!weather || !status) return;

    // WMO weather codes returned by Open-Meteo.
    const descriptions = new Map([
        [0, "☀️ Clear"], [1, "🌤️ Mainly clear"], [2, "⛅ Partly cloudy"],
        [3, "☁️ Overcast"], [45, "🌫️ Fog"], [48, "🌫️ Fog"],
        [51, "🌦️ Drizzle"], [53, "🌦️ Drizzle"], [55, "🌦️ Drizzle"],
        [56, "🌧️ Freezing drizzle"], [57, "🌧️ Freezing drizzle"],
        [61, "🌧️ Rain"], [63, "🌧️ Rain"], [65, "🌧️ Rain"],
        [66, "🌧️ Freezing rain"], [67, "🌧️ Freezing rain"],
        [71, "🌨️ Snow"], [73, "🌨️ Snow"], [75, "🌨️ Snow"], [77, "🌨️ Snow grains"],
        [80, "🌧️ Showers"], [81, "🌧️ Showers"], [82, "🌧️ Showers"],
        [85, "🌨️ Snow showers"], [86, "🌨️ Snow showers"],
        [95, "⛈️ Thunderstorm"], [96, "⛈️ Thunderstorm"], [99, "⛈️ Thunderstorm"],
    ]);

    const url = new URL("https://api.open-meteo.com/v1/forecast");
    url.search = new URLSearchParams({
        latitude: weather.dataset.latitude,
        longitude: weather.dataset.longitude,
        current: "temperature_2m,weather_code,is_day",
        temperature_unit: "celsius",
    }).toString();

    let loading = false;
    const updateWeather = async () => {
        if (loading) return;
        loading = true;
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 10000);
        try {
            const response = await fetch(url, { signal: controller.signal });
            if (!response.ok) throw new Error("Weather request failed");
            const data = await response.json();
            const current = data.current;
            if (!current || !Number.isFinite(current.temperature_2m)
                || !Number.isInteger(current.weather_code)
                || ![0, 1].includes(current.is_day)) {
                throw new Error("Invalid weather response");
            }
            let description = descriptions.get(current.weather_code) || "Weather";
            if (current.is_day === 0 && [0, 1].includes(current.weather_code)) {
                description = "🌙 Clear";
            }
            status.textContent = `${Math.round(current.temperature_2m)}°C · ${description}`;
        } catch {
            // Do not leave old observations looking current after a failed refresh.
            status.textContent = "Weather unavailable";
        } finally {
            window.clearTimeout(timeout);
            loading = false;
        }
    };

    updateWeather();
    window.setInterval(updateWeather, 15 * 60 * 1000);
})();
