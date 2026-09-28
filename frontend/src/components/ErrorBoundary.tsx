import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render errors anywhere below it, so one broken view shows a way
 * out instead of a blank page. API errors are handled where they happen;
 * this is for bugs.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  private reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="page">
        <section className="card error-screen" role="alert">
          <h1>Something went wrong on this page</h1>
          <p>
            Your complaint data is safe: anything already submitted is stored on the server. You can try this page
            again, or reload the app.
          </p>
          <details>
            <summary>Technical details</summary>
            <pre>{error.message}</pre>
          </details>
          <div className="actions">
            <button type="button" onClick={this.reset}>
              Try again
            </button>
            <button type="button" className="secondary" onClick={() => window.location.assign("/")}>
              Reload the app
            </button>
          </div>
        </section>
      </div>
    );
  }
}
