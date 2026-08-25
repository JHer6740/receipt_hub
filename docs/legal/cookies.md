# Cookies and tracking

**Draft — not for publication until legally reviewed.**

**Last updated:** {{EFFECTIVE_DATE}}

## The mobile app

**The Receipt Hub app uses no cookies and no tracking.**

It stores two things on your own device, and neither is a cookie or a tracker:

| What | Where | Why |
|---|---|---|
| Your sign-in token | The device's encrypted storage (Android Keystore) | So you stay signed in and are not asked for your password every time |
| Your settings — colourway, dark mode, larger text, keep-photos | Ordinary app preferences on the device | So your choices survive restarting the app |

Both stay on your device. Neither is sent anywhere except the sign-in token,
which is sent to our own server to prove it is you. Uninstalling the app removes
both.

There is no advertising identifier, no analytics SDK, no third-party SDK that
tracks you, and no cross-app or cross-site tracking.

## The website

{{PUBLIC_DOMAIN}} uses only what it needs to work:

| Cookie | Purpose | Type | Lifetime |
|---|---|---|---|
| Session cookie | Keeps you signed in while using the site | Strictly necessary | Until it expires or you sign out |
| CSRF token | Stops another site submitting forms as you | Strictly necessary | Same as the session |

These are **strictly necessary** — the site cannot function without them — so
under the ePrivacy Directive and equivalent rules they do not require consent.
We do not set any other cookie.

We use **no analytics cookies, no advertising cookies, and no third-party
cookies**. There is nothing optional to consent to, which is why you are not
shown a cookie banner.

### Cloudflare

Traffic to {{PUBLIC_DOMAIN}} is routed through Cloudflare, which encrypts it and
protects the service. Cloudflare may set its own strictly necessary cookies for
security purposes, such as distinguishing automated traffic from real visitors.
See Cloudflare's privacy documentation for what those do.

## Turning them off

Your browser can block or delete cookies — usually under Settings → Privacy.

Blocking the two cookies above will stop you being able to sign in, because they
are how the site knows who you are.

## If this changes

If we ever add a cookie that is not strictly necessary, we will ask for your
consent before setting it, give you a way to change your mind, and update this
page first. We have no plans to add advertising or tracking cookies.

## Questions

{{PRIVACY_EMAIL}}
