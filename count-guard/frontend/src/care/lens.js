// `picked` is {role, lens} or null. A lens picked under another role is stale and is dropped,
// so switching role on an open chart shows that role's own lens.
export function lensFor(role, picked) {
  return picked && picked.role === role ? picked.lens : role;
}
