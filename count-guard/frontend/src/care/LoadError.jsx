// The ward could not load: say so on screens that would otherwise show an empty list.
export default function LoadError({ patients, error }) {
  return !patients.length && error ? <p className="error small" role="alert">{error}</p> : null;
}
