# Project context for the reviewer (example)

Copy this to `.github/ai-review/CONTEXT.md` in your repo and rewrite it for your project. The reviewer reads it on every run, after the rubric. Short and specific beats long.

## What this is

A small Flask app on Railway that lets customers book a slot and pay a deposit through Stripe Checkout. The marketing pages are static files in `static/`.

## Entry points

- `app.py`: all routes. `/book` is public, `/admin/*` needs the admin key.
- `payments.py`: creates Checkout sessions and handles the Stripe webhook at `/stripe/webhook`.
- `static/`: published as plain files.

## Money and customer data

- Deposits go through Stripe. The booking is confirmed only from the verified webhook, never from the success page.
- Customer names and emails live in SQLite at `/data/app.db` (a Railway volume, not in the repo).

## Environment variables (names only)

`ADMIN_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `DATA_DIR`

## Public by design

- The Stripe publishable key in `static/js/book.js`.
- `static/llms.txt` and `static/robots.txt`.

## Known and accepted

- No rate limiting on `/book`. Railway's edge handles abuse for now. Flag it only if a change makes it worse.
