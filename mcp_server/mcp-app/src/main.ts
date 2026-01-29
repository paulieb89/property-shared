import App from "./App.svelte";
import "./global.css";
import { mount } from "svelte";

const app = mount(App, { target: document.getElementById("app")! });

export default app;
