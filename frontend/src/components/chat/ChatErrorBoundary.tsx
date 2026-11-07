import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";

interface State {
  error: Error | null;
}

/**
 * The assistant is optional, so a rendering error inside it must never take the rest of the app
 * down with it. Shows a recoverable message in the panel instead.
 */
export default class ChatErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Assistant crashed:", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <aside className="chat-panel" aria-label="Assistant">
        <div className="chat-empty">
          <Banner
            status="error"
            title="The assistant hit an error"
            description={this.state.error.message}
          />
          <Button
            label="Try again"
            variant="secondary"
            size="sm"
            onClick={() => this.setState({ error: null })}
          />
        </div>
      </aside>
    );
  }
}
