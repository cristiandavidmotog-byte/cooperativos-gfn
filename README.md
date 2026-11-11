# Cooperativos en GeForce NOW (Digevo, Colombia)

Datos semanales para la página "Cooperativos en GeForce NOW".

- `scripts/update.py`: cada lunes, GitHub Actions consulta el catálogo de GeForce NOW (NVIDIA),
  el catálogo de Digevo, Steam (modos de juego, reseñas, precios en Colombia, fechas) y
  PC Game Pass Colombia, y guarda el resultado en `data/games.json`.
- `scripts/merge.py`: une esos datos con la página publicada, conserva los títulos
  (las calificaciones y notas se asocian por título) y escribe un resumen de cambios.

Solo se leen datos públicos. Para correrlo a mano: pestaña **Actions → Actualizar datos → Run workflow**.
