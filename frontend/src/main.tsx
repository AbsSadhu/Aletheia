import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AstryxProvider } from "./lib/AstryxProvider";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "@fontsource-variable/bricolage-grotesque/opsz.css";
import "./styles/tailwind.css";
import "./styles/app.css";
import "./styles/board.css";
import "./styles/system.css";
import "./styles/rail.css";
import "./styles/showcase.css";
import "./styles/pulse.css";
import "./styles/analysis.css";
import "./styles/palette.generated.css";
import { applyTheme, resolveTheme } from "./lib/theme";
import { installTilt } from "./lib/tilt";

applyTheme(resolveTheme());
installTilt();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AstryxProvider>
      <App />
    </AstryxProvider>
  </React.StrictMode>,
);
