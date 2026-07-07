import { registerRootComponent } from "expo";

import App from "./App";

// registerRootComponent calls AppRegistry.registerComponent('main', () => App).
// Without this the app renders a blank screen — App.tsx alone never registers itself.
registerRootComponent(App);
