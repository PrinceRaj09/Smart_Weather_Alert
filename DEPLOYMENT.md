# Split deployment: Vercel frontend + Render API

The split deployment serves the static browser application from Vercel and
keeps Flask, SQLite, uploaded profile pictures, and the existing Jinja pages on
Render. Vercel does **not** proxy requests or serve the UI from Render. The
static build embeds the Render service origin from `RENDER_API_BASE_URL`.

## 1. Deploy the Flask backend on Render

1. Push this repository to GitHub and create a Render **Blueprint** from it.
   Render reads `render.yaml`; the web service runs `gunicorn app:app`.
2. Keep the generated `FLASK_SECRET_KEY`. Do not rotate it casually: changing
   it invalidates existing Flask sessions and split-frontend access tokens.
3. Keep the persistent disk mounted at `/var/data`. The Blueprint stores
   `DATABASE_PATH` at `/var/data/weather_alert.db` and profile pictures at
   `/var/data/profile_pictures`. The Starter service and persistent disk are
   paid Render resources.
4. Note the service URL, for example
   `https://smart-weather-alert.onrender.com`. The API base must be this
   service origin, with no route suffix or trailing slash.
5. Leave `ADMIN_USER_ID` unset until the administrator account is known.
   Admin access is denied when this setting is empty.
6. Configure `VERCEL_ORIGIN` after the Vercel project has its default
   production URL; instructions are below. It must be the exact HTTPS origin,
   for example `https://smart-weather-alert.vercel.app`, without a trailing
   slash. The backend permits only this configured Vercel origin for
   cross-origin API access; it does not use wildcard CORS or credentialed
   cross-origin cookies.

The existing Render-hosted pages remain available at `/`, `/register`,
`/login`, and `/dashboard`. Their same-origin Flask session behavior is
preserved.

## 2. Deploy the static frontend on Vercel

1. Import the same GitHub repository as a Vercel project.
2. Set **Root Directory** to `frontend` and enable inclusion of files outside
   that directory only if Vercel prompts for it. The project uses
   `frontend/vercel.json`; its build produces a plain static `dist` directory.
3. In the Vercel project's **Production** environment variables, add:

   | Name | Value |
   | --- | --- |
   | `RENDER_API_BASE_URL` | The Render service origin from step 1, e.g. `https://smart-weather-alert.onrender.com` |

4. Deploy. The build intentionally fails if `RENDER_API_BASE_URL` is missing
   or is not an HTTPS service origin. Vercel serves the static files directly;
   there is no API rewrite or proxy.
5. Copy the Vercel production origin (not a deployment-specific preview URL)
   and set it as `VERCEL_ORIGIN` in the Render service environment. Save and
   redeploy/restart the Render service. For example:
   `VERCEL_ORIGIN=https://smart-weather-alert.vercel.app`.
6. Test account registration and login from the Vercel URL. For a local
   static build, run `npm run build` from `frontend` with
   `RENDER_API_BASE_URL` set in the environment, then serve `frontend/dist`
   over localhost. Local browser access also requires temporarily configuring
   the backend's single `VERCEL_ORIGIN` as that localhost origin; restore the
   production Vercel origin afterward.

No custom domain is required. The exact Vercel `*.vercel.app` production
origin is the CORS allowlist entry. If the Vercel production URL changes,
update `VERCEL_ORIGIN` on Render and restart the service. Preview deployments
from other origins are deliberately not allowed unless the backend allowlist
is changed to that exact origin. The backend accepts one configured origin at
a time, so use the production Vercel URL for normal service.

## 3. Authentication, storage, and admin access

- Static frontend authentication uses a signed bearer token issued by Flask.
  Tokens are signed with `FLASK_SECRET_KEY` and expire after 45 minutes.
  The browser keeps them only in tab-scoped `sessionStorage`; API calls omit
  cookies and send `Authorization: Bearer …`. Signing out clears the local
  token. Because tokens are stateless, an already-issued token can remain
  valid until expiry if copied elsewhere; keep the secret private and the
  token short-lived.
- CORS allows the exact configured `VERCEL_ORIGIN`, only the API methods and
  headers the frontend needs, and does not allow cross-origin cookies. Render
  same-origin pages continue to use their Flask session cookie.
- SQLite and profile pictures must remain on Render's persistent disk. Do not
  store them in the temporary service filesystem or in the Vercel static
  output.
- To make an account the administrator, register it through the Vercel app
  and sign in. Its Farmer ID appears in the dashboard header. Set that exact
  ID as Render's `ADMIN_USER_ID`, then restart the backend. The account's
  **Admin farmers** button then shows all registered farmer records, searchable
  and paginated 100 records at a time. The server checks the signed-in Farmer
  ID against `ADMIN_USER_ID`; an unset value or any other account is denied.
- Keep the generated `FLASK_SECRET_KEY`, SMTP, and Twilio credentials private.
  Password-reset delivery settings from `.env.example` belong only in Render.
  Never commit `.env` or provider credentials.

The static split frontend currently covers registration, login, farmer
dashboard, profile editing, weather and crop guidance, sign-out, and admin
farmer access. Password reset and profile-picture upload remain available on
the legacy Render-hosted pages but are not part of the static frontend yet.
