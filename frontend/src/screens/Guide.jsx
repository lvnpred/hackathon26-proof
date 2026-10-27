import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Shell } from "../App";

export default function Guide() {
  const [product, setProduct] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/product")
      .then((response) => {
        if (!response.ok) throw new Error("The product map did not load.");
        return response.json();
      })
      .then(setProduct)
      .catch((exc) => setError(exc.message));
  }, []);

  return (
    <Shell>
      <section className="sheet lead">
        <p className="kicker">For a developer and a new reader</p>
        <h2>Where each feature is used.</h2>
        <p>
          {product?.summary || "Count Guard records one morning for one patient."}
          {" "}Open a card to use the feature. The file path is where a developer changes it.
        </p>
        {product && <p className="patient-rule">{product.patient_rule}</p>}
        {error && <p className="error">{error}</p>}
      </section>
      <div className="feature-grid">
        {(product?.features || []).map((feature) => (
          <article className="feature" key={feature.id}>
            <p className="kicker">{feature.where}</p>
            <h2>{feature.title}</h2>
            <p>{feature.use}</p>
            <p className="clock">{feature.api}</p>
            <p className="clock">{feature.code}</p>
            <Link className="go" to={feature.href}>Open {feature.where === "Home" ? "the morning" : feature.title}</Link>
          </article>
        ))}
      </div>
      {product && (
        <section className="panel" style={{ marginTop: 16 }}>
          <h2>Who starts where</h2>
          {product.audiences.map((audience) => (
            <p key={audience.who}>
              <b>{audience.who}.</b> {audience.does}{" "}
              <Link to={audience.start}>Open</Link>
            </p>
          ))}
        </section>
      )}
    </Shell>
  );
}
