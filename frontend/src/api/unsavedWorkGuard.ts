// Bridges client.ts (a plain module — no React, no access to hooks/context) with whatever
// currently has real unsaved work in flight (useDebouncedAutosave, while the editor is mounted).
// Exists for exactly one reason: a forced logout (see client.ts's 401 handling) used to hard-
// redirect to /login with zero regard for whether an edit was mid-save at that exact moment —
// the token dying mid-autosave silently dropped it, no different in kind from the metadata-save
// race this same app already had a real, confirmed bug from. We can't rescue that save (the
// token that would authorize it is the thing that just died), but we can at least tell the user
// honestly that it might not have landed, instead of a silent reload.
let checker: (() => boolean) | null = null;

export function registerUnsavedWorkChecker(fn: () => boolean): void {
  checker = fn;
}

// Callers pass their own function back so a second, unrelated registration can't accidentally
// clear a still-active one (e.g. two editor instances mounting/unmounting in a fast remount).
export function unregisterUnsavedWorkChecker(fn: () => boolean): void {
  if (checker === fn) checker = null;
}

export function hasUnsavedWork(): boolean {
  return checker?.() ?? false;
}
