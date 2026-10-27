# Vendored map dependencies

The site loads these pinned local files. Readers do not contact a CDN or a map
tile provider, and building the site does not download code or geometry.

- `d3-7.9.0.min.js`: D3 7.9.0, https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js.
  ISC license in `LICENSE-d3`.
- `../world-110m.geojson`: country features converted without coordinate changes
  from `@d3-maps/atlas` 1.0.0, `world/countries/countries-110m`.
  Source: https://esm.sh/@d3-maps/atlas@1.0.0/world/countries/countries-110m.
  Conversion: `topojson-client` 3.1.0 `feature(world, world.objects.features)`.
  Atlas license in `LICENSE-atlas`; underlying Natural Earth geometry is public
  domain: https://www.naturalearthdata.com/about/terms-of-use/.

Country ISO3 identifiers come from `feature.properties.id`. Geographic annotations
belong to evidence IDs and are independent of map geometry. Badge positions are
derived from projected country geometry, never fabricated incident coordinates.
