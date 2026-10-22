import { Component } from "react";
import { ErrorState } from "./ErrorState";
export class RouteErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    console.error("Route rendering failed", error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <section className="route-error" aria-labelledby="route-error-title">
          <div className="eyebrow">PAGE UNAVAILABLE</div>
          <h1 id="route-error-title">This page could not be displayed</h1>
          <ErrorState message="Try loading this page again. If the problem continues, refresh the application." />
          <button
            className="btn btn-secondary"
            onClick={() => window.location.reload()}
          >
            Reload application
          </button>
        </section>
      );
    }
    return this.props.children;
  }
}
