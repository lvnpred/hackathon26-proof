// The one rank table of the Now rule (spec 5.1). now.js picks Now with it and derive.js orders the queue rows with it.
// 1 danger (an open safety alert), 2 blocked (a step waits on the viewer), 3 late, 4 due now, 5 review (AI work in its
// undo window; a running task sorts here too), 6 nothing.
export const RANK = { danger: 1, blocked: 2, late: 3, due: 4, review: 5, running: 5, nothing: 6 };
