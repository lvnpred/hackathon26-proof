import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageLead, Shell } from "../App";

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
    <Shell subtitle="Where each feature is used">
      <PageLead
        kicker="For a developer and a new reader"
        title="Where each feature is used."
        body={`${product?.summary || "Count Guard records one morning for one patient."} Open a card to use the feature. The file path is where a developer changes it.`}
      />
      {product && <p className="note" role="note">{product.patient_rule}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!product && !error && <p className="empty">The feature map appears here when it loads.</p>}
      <div className="grid-2">
        {(product?.features || []).map((feature) => (
          <article className="card" key={feature.id}>
            <p className="label">{feature.where}</p>
            <h2>{feature.title}</h2>
            <p>{feature.use}</p>
            <p className="small muted"><code>{feature.api}</code></p>
            <p className="small muted"><code>{feature.code}</code></p>
            <div className="row">
              <Link className="button" to={feature.href}>
                Open {feature.where === "Home" ? "the morning" : feature.title}
              </Link>
            </div>
          </article>
        ))}
      </div>
      {product && (
        <section className="card">
          <p className="label">Who starts where</p>
          <div className="rows">
            {product.audiences.map((audience) => (
              <div className="list-row" key={audience.who}>
                <span>
                  <b>{audience.who}</b>
                  <small>{audience.does}</small>
                </span>
                <Link to={audience.start}>Open</Link>
              </div>
            ))}
          </div>
        </section>
      )}
    </Shell>
  );
}
