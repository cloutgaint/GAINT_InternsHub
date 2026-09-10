import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

export default function CertificateVerify() {
  const { certificateNo } = useParams();
  const [state, setState] = useState({
    loading: true,
    data: null,
    error: "",
  });

  useEffect(() => {
    const controller = new AbortController();

    async function verify() {
      setState({ loading: true, data: null, error: "" });

      try {
        const response = await fetch(
          `${process.env.REACT_APP_CERTIFICATE_VERIFY_BASE_URL}/${encodeURIComponent(certificateNo)}`,
          {
            signal: controller.signal,
            headers: { Accept: "application/json" },
            cache: "no-store",
          }
        );

        if (response.status === 404) {
          setState({
            loading: false,
            data: { valid: false },
            error: "",
          });
          return;
        }

        if (!response.ok) {
          throw new Error(
            "Verification is temporarily unavailable. Please try again."
          );
        }

        const data = await response.json();

        if (!data || typeof data.valid !== "boolean") {
          throw new Error("Unexpected verification response.");
        }

        setState({ loading: false, data, error: "" });
      } catch (error) {
        if (error.name !== "AbortError") {
          setState({
            loading: false,
            data: null,
            error: error.message,
          });
        }
      }
    }

    verify();
    return () => controller.abort();
  }, [certificateNo]);

  const { loading, data, error } = state;
  const valid = data?.valid === true;
  const date = data?.issued_at ? new Date(data.issued_at) : null;

  const issuedOn =
    date && !Number.isNaN(date.getTime())
      ? date.toLocaleDateString("en-IN", {
          day: "2-digit",
          month: "long",
          year: "numeric",
        })
      : "Not provided";

  const details = valid
    ? [
        ["Student name", data.student || "Not provided"],
        ["Certificate number", data.certificate_no || certificateNo],
        ["Project", data.project || "Not provided"],
        ["Technology", data.technology || "Not provided"],
        ...(data.college ? [["College", data.college]] : []),
        ["Issued on", issuedOn],
        ["Issued by", "GAINT Clout Technologies Pvt. Ltd."],
      ]
    : [];

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#f1f5f9",
        padding: "40px 16px",
        boxSizing: "border-box",
        fontFamily: "Arial, sans-serif",
        color: "#0f172a",
      }}
    >
      <article
        style={{
          maxWidth: 720,
          margin: "0 auto",
          background: "#ffffff",
          borderRadius: 20,
          overflow: "hidden",
          boxShadow: "0 12px 40px rgba(15,23,42,0.08)",
        }}
      >
        <header
          style={{
            padding: "28px 24px",
            background: "#0f2747",
            color: "#ffffff",
          }}
        >
          <div style={{ fontSize: 24, fontWeight: 800 }}>
            GAINT Interns Hub
          </div>
          <p style={{ margin: "8px 0 0", color: "#cbd5e1" }}>
            Public Certificate Verification
          </p>
        </header>

        <section style={{ padding: 24 }} aria-live="polite">
          {loading ? (
            <p role="status">Checking certificate details…</p>
          ) : error ? (
            <>
              <h1 style={{ fontSize: 26 }}>Unable to verify right now</h1>
              <p style={{ lineHeight: 1.6 }}>{error}</p>
              <button
                onClick={() => window.location.reload()}
                style={{
                  background: "#0f2747",
                  color: "#ffffff",
                  border: 0,
                  borderRadius: 8,
                  padding: "12px 20px",
                  cursor: "pointer",
                }}
              >
                Try again
              </button>
            </>
          ) : valid ? (
            <>
              <div
                style={{
                  background: "#ecfdf5",
                  border: "1px solid #a7f3d0",
                  borderRadius: 12,
                  padding: 20,
                  marginBottom: 24,
                }}
              >
                <h1
                  style={{
                    margin: "0 0 8px",
                    color: "#047857",
                    fontSize: 28,
                  }}
                >
                  ✓ Certificate Verified
                </h1>
                <p style={{ margin: 0, lineHeight: 1.6 }}>
                  This certificate is recorded as valid in GAINT Interns Hub.
                </p>
              </div>

              <dl style={{ margin: 0 }}>
                {details.map(([label, value]) => (
                  <div
                    key={label}
                    style={{
                      padding: "16px 0",
                      borderBottom: "1px solid #e2e8f0",
                    }}
                  >
                    <dt
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: "#64748b",
                        marginBottom: 7,
                      }}
                    >
                      {label}
                    </dt>
                    <dd
                      style={{
                        margin: 0,
                        fontSize: 17,
                        lineHeight: 1.5,
                        overflowWrap: "anywhere",
                      }}
                    >
                      {String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </>
          ) : (
            <div
              style={{
                padding: 20,
                borderRadius: 12,
                background: "#fff1f2",
                border: "1px solid #fecdd3",
              }}
            >
              <h1 style={{ color: "#be123c", fontSize: 26 }}>
                Certificate Not Verified
              </h1>
              <p style={{ lineHeight: 1.6 }}>
                This certificate could not be confirmed as valid. Check the
                certificate number or contact GAINT for assistance.
              </p>
            </div>
          )}

          <p
            style={{
              marginTop: 24,
              fontSize: 13,
              color: "#64748b",
              lineHeight: 1.6,
            }}
          >
            GAINT Interns Hub test environment.
          </p>
        </section>
      </article>
    </main>
  );
}