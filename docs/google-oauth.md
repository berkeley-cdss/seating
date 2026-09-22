# Google OAuth Login Setup

The seating app supports Google OAuth as a **secondary** sign-in option
alongside Canvas. Google login is only used to authenticate **existing**
users — a Google sign-in will never create a new account. Users must
first sign in via Canvas at least once to establish their account, after
which they may sign in with the Google account that matches their
Canvas email.

This makes Google OAuth useful when:

- A user's Canvas access has lapsed (e.g. course ended) but they still
  need to access historical seating data.
- Staff prefer a faster sign-in flow than the full Canvas OAuth
  round-trip.

If Google credentials are not configured (i.e. `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET` are blank), the Google option is hidden and the
login flow falls back to Canvas-only — exactly the same as before.

## 1. Create the OAuth client in Google Cloud Console

1. Open the [Google Cloud Console](https://console.cloud.google.com/)
   and select (or create) the project you want to host the OAuth
   client in. The seating app already uses a Google Cloud project for
   the Google Sheets service account (see `GCP_SA_CRED_*` settings);
   you can reuse that project or create a new one.
2. In the left nav, go to **APIs & Services → OAuth consent screen**
   and configure the consent screen if you have not already:
   - User type: **Internal** if your organization uses Google
     Workspace and you only want users on that domain (recommended for
     `berkeley.edu`). Otherwise use **External**.
   - App name, support email, developer email: required fields.
   - Scopes: add `openid`, `.../auth/userinfo.email`, and
     `.../auth/userinfo.profile`. No other scopes are required by the
     seating app.
3. In the left nav, go to **APIs & Services → Credentials** and click
   **Create Credentials → OAuth client ID**.
4. Application type: **Web application**.
5. Name: anything recognizable, e.g. *Seating App – Production*.
6. **Authorized JavaScript origins**: add the root URL of every
   environment that needs to sign in. Examples:
   - `https://seating.example.edu`
   - `http://localhost:5000` (development only)
7. **Authorized redirect URIs**: add the full callback URL for every
   environment. The path is fixed at `/authorized/google/`. Examples:
   - `https://seating.example.edu/authorized/google/`
   - `http://localhost:5000/authorized/google/` (development only)

   The trailing slash matters — it must match the Flask route exactly.
8. Click **Create**. Google will show you a **Client ID** and **Client
   secret** — copy both. (You can retrieve them again later from the
   same Credentials page.)

## 2. Configure the seating app

Add the following variables to your environment (`.env` file in
development, your hosting platform's secret store in production). See
[`.env.sample`](../.env.sample) for the full list.

```bash
# OAuth Client ID issued by Google Cloud Console.
GOOGLE_CLIENT_ID=1234567890-abc...apps.googleusercontent.com

# OAuth Client secret issued by Google Cloud Console.
GOOGLE_CLIENT_SECRET=GOCSPX-...

# Optional: restrict sign-ins to one or more Google Workspace domains.
# Comma-separated; leave blank to accept any Google account whose email
# matches a known user. Highly recommended in production.
GOOGLE_HOSTED_DOMAINS=berkeley.edu
```

Restart the Flask app. The login page (`/login/`) will now show a
"Sign in with Google" button next to the existing "Sign in with
Canvas" option.

## 3. How the matching works

When a user signs in with Google, the app:

1. Verifies the Google token and reads the user's email and unique
   Google account id (the OpenID `sub` claim).
2. Rejects unverified emails (`email_verified=false`).
3. If `GOOGLE_HOSTED_DOMAINS` is set, rejects any email whose Google
   Workspace domain (`hd` claim or, as a fallback, the email's domain
   suffix) is not in the allow-list.
4. Looks up an existing `User` row by Google account id first, then
   falls back to a case-insensitive email match against the `email`
   column populated during Canvas sign-in.
5. If no matching user is found, the sign-in is rejected with a
   flashed message instructing the user to log in via Canvas first.
   **No new user record is created.**
6. On the first successful match by email, the Google account id is
   stored on the user so subsequent sign-ins are bound to the stable
   identifier and survive email-address changes.

## 4. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| The Google button does not appear on `/login/`. | `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` is unset; the server was not restarted; or you are in `MOCK_CANVAS=true` mode, which redirects to the dev login screen. |
| "redirect_uri_mismatch" error from Google. | The redirect URI registered in Google Cloud Console must exactly match `${SERVER_BASE_URL}/authorized/google/` (including scheme, host, port, and trailing slash). |
| "No account is associated with this Google email." | The user has never signed in with Canvas (so the app does not know their email), or the Google email differs from what Canvas reported. Ask the user to sign in with Canvas first. |
| "Your Google domain is not permitted to sign in here." | The user's Google Workspace domain is not in `GOOGLE_HOSTED_DOMAINS`. Add it, or have them sign in with Canvas instead. |
| Domain restriction is bypassed for personal Gmail accounts. | Personal Gmail accounts do not have an `hd` claim. The fallback uses the email suffix, so `something@gmail.com` will only be allowed if `gmail.com` is explicitly listed in `GOOGLE_HOSTED_DOMAINS`. |
