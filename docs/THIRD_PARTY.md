# Third-party assets

The local interface uses the Sky and Slate CSS scales from `@radix-ui/colors` version `3.0.0`, licensed under MIT. The source package is available from the [npm registry](https://www.npmjs.com/package/@radix-ui/colors/v/3.0.0); usage guidance is in the [Radix Colors documentation](https://www.radix-ui.com/colors/docs/overview/installation).

`src/terraforma/static/radix-colors.css` bundles `sky.css`, `sky-dark.css`, `slate.css`, and `slate-dark.css`. Their selectors are adapted to the app's default dark mode and `data-theme="light"` attribute. The color values, including Display P3 variants, are preserved. The accompanying `radix-colors-LICENSE.txt` is included in the installed Python package.

The palette is served locally. Using the interface requires no npm installation, remote stylesheets, or frontend build step.
