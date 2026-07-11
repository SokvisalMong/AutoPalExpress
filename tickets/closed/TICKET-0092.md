# TICKET-0092

**Status**

Closed

**Type**

Bug

**Priority**

Medium

**Created**

2026-07-11

---

## Description

The Dashboard roster on `/` only fetched players once when the page mounted. A player who joined after the dashboard loaded remained marked offline until the browser was refreshed.

## Reason

The roster must reflect real Palworld REST player state while the Dashboard is open, including a player becoming online after joining the server.

## Implementation Plan

* [x] Poll the roster on a one-second cadence while the Dashboard is mounted.

* [x] Avoid overlapping requests and stop polling cleanly when the component unmounts.

* [x] Preserve the existing initial loading and error behavior.

## Files Modified

* `web/src/components/players/PlayersSection.tsx`

## Testing

* `npm run build` (passed; TypeScript and Vite production build).
* `npm run lint` (passed with five pre-existing warnings in unrelated files; no diagnostic in `PlayersSection.tsx`).

## Result

The Dashboard roster now fetches immediately and schedules the next request one second after each request completes. A player who joins after the page loads is reflected without a manual refresh. In-flight polling is cancelled on unmount, and repeated failures do not spam notifications after the initial request.

## Notes

Uses the existing recursive-timeout polling style from `useServerStatus` so a slow `/api/players` request cannot overlap the next poll.

## Closed

2026-07-11
