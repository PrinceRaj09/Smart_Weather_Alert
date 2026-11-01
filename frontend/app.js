(() => {
  const app = document.getElementById("app");
  const topActions = document.getElementById("top-actions");
  const toast = document.getElementById("toast");
  const tokenKey = "swa-access-token";
  const apiBase = window.SWA_CONFIG?.apiBaseUrl;
  const soils = ["Alluvial", "Black", "Clay", "Laterite", "Loamy", "Red", "Sandy"];
  let token = sessionStorage.getItem(tokenKey) || "";
  let farmerProfile = null;
  let adminPage = 1;
  let adminSearch = "";
  let toastTimer;

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3600);
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (options.body && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers,
      credentials: "omit"
    });
    const contentType = response.headers.get("content-type") || "";
    const result = contentType.includes("application/json")
      ? await response.json()
      : {};

    if (!response.ok) {
      if (response.status === 401 && token && !path.startsWith("/api/auth/")) {
        clearToken();
        renderWelcome();
      }
      throw new Error(result.message || `Request failed (${response.status}).`);
    }
    return result;
  }

  function setToken(value) {
    token = value;
    sessionStorage.setItem(tokenKey, value);
  }

  function clearToken() {
    token = "";
    sessionStorage.removeItem(tokenKey);
    farmerProfile = null;
  }

  function setTopActions(authenticated = false) {
    topActions.className = "top-actions";
    topActions.innerHTML = authenticated
      ? '<button class="button secondary small" id="logout-button" type="button">Sign out</button>'
      : '<button class="button quiet small" data-auth-mode="login" type="button">Log in</button>' +
        '<button class="button small" data-auth-mode="register" type="button">Create account</button>';
  }

  function renderWelcome(mode = "login") {
    setTopActions(false);
    const registration = mode === "register";
    app.innerHTML = `
      <section class="welcome">
        <div class="welcome-copy">
          <div class="eyebrow">Practical weather intelligence for farmers</div>
          <h1>Plan each day<br>with <span>confidence.</span></h1>
          <p class="lead">Local forecasts, timely weather alerts and crop guidance—all in one place for your farm.</p>
          <ul class="feature-list">
            <li><span>◷</span> Hourly weather outlook and field alerts</li>
            <li><span>⌂</span> A profile built around your farm location</li>
            <li><span>✦</span> Soil-aware crop suggestions</li>
          </ul>
        </div>
        <section class="auth-card" aria-labelledby="auth-title">
          <div class="eyebrow">${registration ? "Join AgriWeather" : "Welcome back"}</div>
          <h2 id="auth-title">${registration ? "Create your farmer account" : "Sign in to your farm"}</h2>
          <p>${registration
            ? "Add your farm details to receive relevant local guidance."
            : "Your weather dashboard is ready when you are."}</p>
          <form id="auth-form">
            ${registration ? registrationFields() : loginFields()}
            <p class="form-message" id="form-message" role="status"></p>
            <button class="button form-submit" type="submit">
              ${registration ? "Create account" : "Log in"}
            </button>
          </form>
          <div class="auth-switch">
            ${registration ? "Already registered?" : "New to AgriWeather?"}
            <button class="link-button" id="switch-auth" type="button">
              ${registration ? "Log in" : "Create an account"}
            </button>
          </div>
        </section>
      </section>`;

    document.querySelectorAll("[data-auth-mode]").forEach((button) => {
      button.addEventListener("click", () => renderWelcome(button.dataset.authMode));
    });
    document.getElementById("switch-auth").addEventListener("click", () => {
      renderWelcome(registration ? "login" : "register");
    });
    document.getElementById("auth-form").addEventListener("submit", (event) => {
      event.preventDefault();
      submitAuth(event.currentTarget, registration);
    });
    if (registration) bindLocationButton();
  }

  function registrationFields() {
    return `
      <div class="form-grid">
        <div class="field"><label for="full_name">Full name</label>
          <input id="full_name" name="full_name" autocomplete="name" maxlength="100" required></div>
        <div class="field"><label for="phone">Mobile number</label>
          <input id="phone" name="phone" type="tel" inputmode="numeric" pattern="[6-9][0-9]{9}" maxlength="10" required></div>
        <div class="field full"><label for="email">Email address</label>
          <input id="email" name="email" type="email" autocomplete="email" maxlength="254" required></div>
        <div class="field"><label for="password">Password (8+ characters)</label>
          <input id="password" name="password" type="password" minlength="8" autocomplete="new-password" required></div>
        <div class="field"><label for="confirm_password">Confirm password</label>
          <input id="confirm_password" name="confirm_password" type="password" minlength="8" autocomplete="new-password" required></div>
        <div class="field full"><label>Farm location</label>
          <div class="location-row">
            <button class="button secondary small" id="detect-location" type="button">Detect GPS location</button>
            <span class="location-status" id="location-status">Required to register</span>
          </div>
          <input type="hidden" name="latitude" id="latitude">
          <input type="hidden" name="longitude" id="longitude">
        </div>
        <div class="field"><label for="state">State</label>
          <input id="state" name="state" maxlength="100" required></div>
        <div class="field"><label for="district">District</label>
          <input id="district" name="district" maxlength="100" required></div>
        <div class="field"><label for="village">Village</label>
          <input id="village" name="village" maxlength="100" required></div>
        <div class="field"><label for="pin_code">PIN code</label>
          <input id="pin_code" name="pin_code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required></div>
        <div class="field"><label for="farming_type">Farming type</label>
          <select id="farming_type" name="farming_type" required>
            <option value="">Select type</option><option>Crop farming</option>
          </select></div>
        <div class="field"><label for="farm_size">Farm size (acres)</label>
          <input id="farm_size" name="farm_size" type="number" min="0.01" step="any" required></div>
        <div class="field"><label for="crops">Main crops</label>
          <input id="crops" name="crops" maxlength="500" required></div>
        <div class="field"><label for="soil_type">Soil type</label>
          <select id="soil_type" name="soil_type" required>
            <option value="">Select soil</option>
            ${soils.map((soil) => `<option>${soil}</option>`).join("")}
          </select></div>
      </div>`;
  }

  function loginFields() {
    return `
      <div class="form-grid">
        <div class="field full"><label for="identifier">Farmer ID, mobile or email</label>
          <input id="identifier" name="identifier" autocomplete="username" required></div>
        <div class="field full"><label for="password">Password</label>
          <input id="password" name="password" type="password" autocomplete="current-password" required></div>
      </div>`;
  }

  function bindLocationButton() {
    const button = document.getElementById("detect-location");
    const status = document.getElementById("location-status");
    button.addEventListener("click", () => {
      if (!navigator.geolocation) {
        status.textContent = "Location is not supported by this browser.";
        return;
      }
      button.disabled = true;
      status.textContent = "Finding your location…";
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          document.getElementById("latitude").value = coords.latitude;
          document.getElementById("longitude").value = coords.longitude;
          status.textContent = `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`;
          button.disabled = false;
        },
        () => {
          status.textContent = "Location unavailable. Allow GPS and try again.";
          button.disabled = false;
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
      );
    });
  }

  async function submitAuth(form, registration) {
    const message = document.getElementById("form-message");
    const submit = form.querySelector('[type="submit"]');
    message.textContent = "";
    const values = Object.fromEntries(new FormData(form).entries());
    if (registration && (!values.latitude || !values.longitude)) {
      message.textContent = "Detect your farm's GPS location before registering.";
      return;
    }
    submit.disabled = true;
    try {
      const result = await api(
        registration ? "/api/auth/register" : "/api/auth/login",
        { method: "POST", body: JSON.stringify(values) }
      );
      setToken(result.access_token);
      showToast(registration ? "Account created successfully." : "Welcome back.");
      await loadDashboard();
    } catch (error) {
      message.textContent = error.message;
    } finally {
      if (submit.isConnected) submit.disabled = false;
    }
  }

  function fieldValue(profile, key) {
    return escapeHtml(profile[key]);
  }

  function profileForm(profile) {
    const fields = [
      ["full_name", "Full name", "text", true],
      ["phone", "Mobile", "tel", true],
      ["email", "Email", "email", true],
      ["state", "State", "text", true],
      ["district", "District", "text", true],
      ["village", "Village", "text", true],
      ["pin_code", "PIN code", "text", true],
      ["farming_type", "Farming type", "text", true],
      ["farm_size", "Farm size (acres)", "number", true],
      ["crops", "Main crops", "text", true],
      ["soil_type", "Soil type", "select", true],
      ["latitude", "Latitude", "number", false],
      ["longitude", "Longitude", "number", false]
    ];
    return fields.map(([key, label, type, required]) => {
      const value = fieldValue(profile, key);
      const control = type === "select"
        ? `<select id="edit-${key}" name="${key}" ${required ? "required" : ""}>
            ${soils.map((soil) => `<option ${String(profile[key] || "").toLowerCase() === soil.toLowerCase() ? "selected" : ""}>${soil}</option>`).join("")}
          </select>`
        : `<input id="edit-${key}" name="${key}" type="${type}" value="${value}"
            ${type === "number" && key === "farm_size" ? 'min="0.01" step="any"' : ""}
            ${type === "number" && key !== "farm_size" ? 'step="any"' : ""}
            ${required ? "required" : ""}>`;
      return `<div class="field"><label for="edit-${key}">${label}</label>${control}</div>`;
    }).join("");
  }

  function displayWeather(result) {
    if (!result) {
      return '<div class="empty-state">Weather could not be loaded. Check your saved farm location and try again.</div>';
    }
    const data = result.weather;
    const temperature = data.temperature_2m;
    const units = data.units || {};
    const forecasts = data.forecast || {};
    const currentTime = data.time || "";
    const times = forecasts.time || [];
    const future = times.map((time, index) => ({ time, index }))
      .filter((entry) => !currentTime || entry.time >= currentTime)
      .slice(0, 4);
    const cards = future.length ? future.map(({ time, index }) => `
      <div class="hour-item">
        <small>${escapeHtml(time.replace("T", " ").slice(5, 16))}</small>
        <strong>${escapeHtml(forecasts.temperature_2m?.[index] ?? "—")}°</strong>
        <span>${escapeHtml(forecasts.precipitation?.[index] ?? 0)} mm rain</span>
      </div>`).join("") : '<div class="empty-state">Hourly outlook unavailable.</div>';
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];
    const alertItems = alerts.map((alert) => `
      <div class="alert-item ${String(alert.level).toLowerCase() === "danger" ? "danger" : String(alert.level).toLowerCase() === "warning" ? "warning" : ""}">
        <strong>${escapeHtml(alert.title)}</strong><p>${escapeHtml(alert.message)}</p>
      </div>`).join("");
    const suggestions = data.crop_suggestions?.recommendations || [];
    const cropItems = suggestions.length ? suggestions.map((item) => `
      <div class="crop-item"><div><strong>${escapeHtml(item.crop)}</strong><p>${escapeHtml(item.reason)}</p></div>
        <span>${escapeHtml(item.weather_fit)}</span></div>`).join("")
      : '<div class="empty-state">Crop suggestions are unavailable right now.</div>';

    return `
      <div class="weather-current">
        <div class="temperature">${escapeHtml(temperature ?? "—")}°</div>
        <div class="weather-details">
          ${weatherMetric("Humidity", data.relative_humidity_2m, units.relative_humidity_2m || "%")}
          ${weatherMetric("Rain", data.precipitation, units.precipitation || "mm")}
          ${weatherMetric("Wind", data.wind_speed_10m, units.wind_speed_10m || "km/h")}
          ${weatherMetric("Updated", currentTime.replace("T", " ").slice(0, 16), "")}
        </div>
      </div>
      <div class="hour-list">${cards}</div>`;
  }

  function weatherMetric(label, value, unit) {
    return `<div class="weather-detail"><small>${escapeHtml(label)}</small><strong>${escapeHtml(value ?? "—")} ${escapeHtml(unit)}</strong></div>`;
  }

  function renderDashboard(profileResult, weatherResult, weatherError = "") {
    farmerProfile = profileResult.profile;
    const profile = farmerProfile;
    const farmerName = escapeHtml(profile.full_name || "Farmer");
    const weatherMarkup = weatherResult
      ? displayWeather(weatherResult)
      : `<div class="empty-state">${escapeHtml(weatherError || "Weather could not be loaded.")}</div>
         <button class="button secondary small" id="retry-weather" type="button">Refresh weather</button>`;
    const weatherData = weatherResult?.weather;
    const alertItems = weatherData?.alerts?.length
      ? weatherData.alerts.map((alert) => `
          <div class="alert-item ${String(alert.level).toLowerCase() === "danger" ? "danger" : String(alert.level).toLowerCase() === "warning" ? "warning" : ""}">
            <strong>${escapeHtml(alert.title)}</strong><p>${escapeHtml(alert.message)}</p>
          </div>`).join("")
      : '<div class="empty-state">Weather alerts will appear here.</div>';
    const suggestions = weatherData?.crop_suggestions?.recommendations || [];
    const crops = suggestions.length
      ? suggestions.map((item) => `
          <div class="crop-item"><div><strong>${escapeHtml(item.crop)}</strong><p>${escapeHtml(item.reason)}</p></div>
            <span>${escapeHtml(item.weather_fit)}</span></div>`).join("")
      : '<div class="empty-state">Crop suggestions are unavailable right now.</div>';

    setTopActions(true);
    app.innerHTML = `
      <section class="dashboard-head">
        <div><div class="eyebrow">Your farm overview · ${escapeHtml(profile.user_id)}</div>
          <h1>Good day, ${farmerName}</h1>
          <p>${escapeHtml([profile.village, profile.district, profile.state].filter(Boolean).join(", "))}</p></div>
        ${profile.is_admin ? '<button class="button secondary" id="admin-toggle" type="button">Admin farmers</button>' : ""}
      </section>
      <section class="dashboard-grid">
        <article class="panel weather-panel">
          <h2>Farm weather</h2><p class="panel-subtitle">Current conditions and the next hourly outlook</p>
          <div id="weather-content">${weatherMarkup}</div>
        </article>
        <article class="panel alerts-panel">
          <h2>Weather alerts</h2><p class="panel-subtitle">Current guidance for your farm</p>
          <div class="alert-list">${alertItems}</div>
          ${weatherData?.forecast_alerts?.length
            ? `<p class="panel-subtitle" style="margin-top:14px">Forecast: ${weatherData.forecast_alerts.map((a) => escapeHtml(a.title)).join(" · ")}</p>`
            : ""}
        </article>
        <article class="panel profile-panel">
          <h2>Farmer profile</h2><p class="panel-subtitle">Your details and saved farm preferences</p>
          <div class="profile-summary">
            <span class="profile-tag">🌱 ${escapeHtml(profile.soil_type)} soil</span>
            <span class="profile-tag">🚜 ${escapeHtml(profile.farm_size)} acres</span>
            <span class="profile-tag">🌾 ${escapeHtml(profile.crops)}</span>
          </div>
          <div class="profile-fields" id="profile-values">
            ${[
              ["Mobile", profile.phone], ["Email", profile.email],
              ["Farm location", [profile.village, profile.district, profile.state, profile.pin_code].filter(Boolean).join(", ")],
              ["Farming type", profile.farming_type],
              ["GPS coordinates", [profile.latitude, profile.longitude].filter((v) => v !== null && v !== undefined).join(", ")]
            ].map(([label, value]) => `<div class="profile-value"><small>${escapeHtml(label)}</small><strong>${escapeHtml(value || "Not set")}</strong></div>`).join("")}
          </div>
          <form id="profile-edit-form" hidden>
            <div class="profile-fields">${profileForm(profile)}</div>
            <div class="profile-form-actions">
              <button class="button small" type="submit">Save changes</button>
              <button class="button secondary small" id="cancel-edit" type="button">Cancel</button>
            </div>
            <p class="form-message" id="profile-message" role="status"></p>
          </form>
          <button class="button secondary small" id="edit-profile" type="button">Edit profile</button>
        </article>
        <article class="panel crops-panel">
          <h2>Crop suggestions</h2><p class="panel-subtitle">Recommendations for your soil and current conditions</p>
          <div class="crop-list">${crops}</div>
          ${weatherData?.crop_suggestions?.note ? `<p class="panel-subtitle" style="margin-top:12px">${escapeHtml(weatherData.crop_suggestions.note)}</p>` : ""}
        </article>
        <article class="panel admin-panel" id="admin-panel" hidden>
          <h2>Registered farmers</h2><p class="panel-subtitle">This list is available only to the account configured as ADMIN_USER_ID.</p>
          <form class="admin-toolbar" id="admin-search-form">
            <input class="search-input" name="search" value="${escapeHtml(adminSearch)}" placeholder="Search farmer, ID, phone or email">
            <button class="button small" type="submit">Search</button>
            <span id="admin-count" class="panel-subtitle"></span>
          </form>
          <div id="admin-results"><div class="empty-state">Loading registered farmer data…</div></div>
        </article>
      </section>`;

    document.getElementById("logout-button").addEventListener("click", logout);
    document.getElementById("edit-profile").addEventListener("click", () => {
      document.getElementById("profile-values").hidden = true;
      document.getElementById("edit-profile").hidden = true;
      document.getElementById("profile-edit-form").hidden = false;
    });
    document.getElementById("cancel-edit").addEventListener("click", () => {
      document.getElementById("profile-edit-form").hidden = true;
      document.getElementById("profile-values").hidden = false;
      document.getElementById("edit-profile").hidden = false;
    });
    document.getElementById("profile-edit-form").addEventListener("submit", saveProfile);
    document.getElementById("admin-toggle")?.addEventListener("click", toggleAdmin);
    document.getElementById("admin-search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      adminSearch = new FormData(event.currentTarget).get("search").trim();
      adminPage = 1;
      loadAdminFarmers();
    });
    document.getElementById("retry-weather")?.addEventListener("click", refreshWeather);
  }

  async function loadDashboard() {
    app.innerHTML = '<div class="loading-card">Loading your farm dashboard…</div>';
    try {
      const profile = await api("/api/profile");
      let weather = null;
      let weatherError = "";
      try {
        weather = await api("/api/my-weather");
      } catch (error) {
        if (!token) return;
        weatherError = error.message;
      }
      renderDashboard(profile, weather, weatherError);
    } catch (error) {
      if (token) {
        showToast(error.message);
        renderWelcome();
      }
    }
  }

  async function refreshWeather() {
    const button = document.getElementById("retry-weather");
    if (button) button.disabled = true;
    try {
      const result = await api("/api/my-weather");
      const profile = await api("/api/profile");
      renderDashboard(profile, result);
    } catch (error) {
      showToast(error.message);
    }
  }

  async function saveProfile(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const message = document.getElementById("profile-message");
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    message.textContent = "";
    try {
      const values = Object.fromEntries(new FormData(form).entries());
      const result = await api("/api/profile", {
        method: "POST",
        body: JSON.stringify(values)
      });
      showToast(result.message || "Profile saved.");
      const profile = await api("/api/profile");
      let weather = null;
      try { weather = await api("/api/my-weather"); } catch { /* Profile still updates if weather is unavailable. */ }
      renderDashboard(profile, weather);
    } catch (error) {
      message.textContent = error.message;
      submit.disabled = false;
    }
  }

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (error) {
      showToast(error.message);
    } finally {
      clearToken();
      renderWelcome();
    }
  }

  async function toggleAdmin() {
    const panel = document.getElementById("admin-panel");
    panel.hidden = !panel.hidden;
    if (!panel.hidden) {
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
      await loadAdminFarmers();
    }
  }

  async function loadAdminFarmers() {
    const results = document.getElementById("admin-results");
    const count = document.getElementById("admin-count");
    if (!results) return;
    results.innerHTML = '<div class="empty-state">Loading registered farmer data…</div>';
    const query = new URLSearchParams({ page: String(adminPage), search: adminSearch });
    try {
      const data = await api(`/api/admin/farmers?${query}`);
      count.textContent = `${data.total} registered farmer${data.total === 1 ? "" : "s"}`;
      const rows = data.farmers.map((farmer) => `
        <tr>
          <td>${escapeHtml(farmer.user_id)}</td><td>${escapeHtml(farmer.full_name)}</td>
          <td>${escapeHtml(farmer.phone)}</td><td>${escapeHtml(farmer.email)}</td>
          <td>${escapeHtml([farmer.village, farmer.district, farmer.state, farmer.pin_code].filter(Boolean).join(", "))}</td>
          <td>${escapeHtml([farmer.latitude, farmer.longitude].filter((value) => value !== null && value !== undefined).join(", ") || "Not set")}</td>
          <td>${escapeHtml(farmer.farming_type)}</td><td>${escapeHtml(farmer.farm_size)} acres</td>
          <td>${escapeHtml(farmer.crops)}</td><td>${escapeHtml(farmer.soil_type)}</td>
          <td>${escapeHtml(farmer.created_at)}</td>
          <td>
            <strong>${Number(farmer.login_count) || 0}</strong>
            <small class="login-last-seen">${farmer.last_login_at
              ? `Last: ${formatLoginTimestamp(farmer.last_login_at)}`
              : "Never logged in"}</small>
            <button class="button secondary small login-history-toggle"
              type="button" data-user-id="${escapeHtml(farmer.user_id)}"
              ${Number(farmer.login_count) ? "" : "disabled"}>View history</button>
            <div class="login-history-panel" hidden></div>
          </td>
        </tr>`).join("");
      results.innerHTML = data.farmers.length
        ? `<div class="table-wrap"><table class="farmers-table">
             <thead><tr><th>Farmer ID</th><th>Name</th><th>Phone</th><th>Email</th><th>Location</th><th>GPS coordinates</th><th>Farm type</th><th>Size</th><th>Crops</th><th>Soil</th><th>Registered</th><th>Login activity</th></tr></thead>
             <tbody>${rows}</tbody></table></div>
           <div class="admin-pages">
             <button class="button secondary small" id="admin-prev" ${adminPage <= 1 ? "disabled" : ""}>Previous</button>
             <span>Page ${data.page} · ${data.page_size} per page</span>
             <button class="button secondary small" id="admin-next" ${adminPage * data.page_size >= data.total ? "disabled" : ""}>Next</button>
           </div>`
        : '<div class="empty-state">No farmer records match this search.</div>';
      document.getElementById("admin-prev")?.addEventListener("click", () => {
        adminPage = Math.max(1, adminPage - 1);
        loadAdminFarmers();
      });
      document.getElementById("admin-next")?.addEventListener("click", () => {
        adminPage += 1;
        loadAdminFarmers();
      });
      results.querySelectorAll(".login-history-toggle").forEach((button) => {
        button.addEventListener("click", async () => {
          const panel = button.parentElement.querySelector(".login-history-panel");
          panel.hidden = !panel.hidden;
          if (!panel.hidden && panel.dataset.loaded !== "true") {
            await loadFarmerLoginHistory(button.dataset.userId, 1, panel);
          }
        });
      });
    } catch (error) {
      count.textContent = "";
      results.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  }

  function formatLoginTimestamp(timestamp) {
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime())
      ? escapeHtml(timestamp)
      : escapeHtml(date.toLocaleString());
  }

  async function loadFarmerLoginHistory(userId, page, panel) {
    panel.innerHTML = '<div class="empty-state">Loading login history…</div>';
    try {
      const query = new URLSearchParams({ page: String(page) });
      const data = await api(
        `/api/admin/farmers/${encodeURIComponent(userId)}/logins?${query}`
      );
      const entries = data.logins.map((login) =>
        `<li>${formatLoginTimestamp(login.logged_in_at)}</li>`
      ).join("");
      const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
      panel.innerHTML = `
        <strong>Successful logins · ${data.total}</strong>
        ${entries ? `<ol>${entries}</ol>` : '<p>No login records yet.</p>'}
        ${totalPages > 1 ? `
          <div class="login-history-pages">
            <button class="button secondary small" data-history-page="${data.page - 1}"
              ${data.page <= 1 ? "disabled" : ""}>Previous</button>
            <span>Page ${data.page} of ${totalPages} · local time</span>
            <button class="button secondary small" data-history-page="${data.page + 1}"
              ${data.page >= totalPages ? "disabled" : ""}>Next</button>
          </div>` : '<small>Times shown in your local timezone.</small>'}`;
      panel.dataset.loaded = "true";
      panel.querySelectorAll("[data-history-page]").forEach((button) => {
        button.addEventListener("click", () => {
          loadFarmerLoginHistory(userId, Number(button.dataset.historyPage), panel);
        });
      });
    } catch (error) {
      panel.dataset.loaded = "false";
      panel.innerHTML = `<p class="form-message">${escapeHtml(error.message)}</p>`;
    }
  }

  if (!apiBase) {
    app.innerHTML = '<div class="empty-state">Frontend API URL is not configured. Set RENDER_API_BASE_URL in the Vercel project and redeploy.</div>';
    return;
  }

  if (token) loadDashboard();
  else renderWelcome();
})();
