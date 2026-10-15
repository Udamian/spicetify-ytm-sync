/**
 * Spike S3: Validar acceso a localhost desde el web view de Spotify (DevTools).
 *
 * Instrucciones:
 * 1. Con el companion corriendo (http://127.0.0.1:48215)
 * 2. Abre Spotify (las DevTools están habilitadas con Ctrl+Shift+I o F12 o clic derecho -> Inspeccionar)
 * 3. En la pestaña 'Console' de DevTools, copia y pega este script.
 */

(async () => {
  console.group("=== Spike S3: Localhost desde Spicetify ===");

  // 1. Origen real del cliente
  const origin = window.location.origin;
  console.log("1. location.origin:", origin);
  const expectedOrigin = "https://xpui.app.spotify.com";
  if (origin === expectedOrigin) {
    console.log("   ✅ Coincide con el origen esperado en el companion:", expectedOrigin);
  } else {
    console.warn(`   ⚠️ Origen inesperado: "${origin}" (companion espera "${expectedOrigin}").`);
  }

  // 2. Comprobar /health (GET sin auth, valida fetch a 127.0.0.1 y CORS/PNA)
  try {
    const healthRes = await fetch("http://127.0.0.1:48215/health");
    const healthData = await healthRes.json();
    console.log("2. GET /health respuesta:", healthData);
    if (healthRes.ok && healthData.ok) {
      console.log("   ✅ fetch a 127.0.0.1 funciona correctamente desde el web view.");
    } else {
      console.error("   ❌ GET /health devolvió un error:", healthRes.status, healthData);
    }
  } catch (err) {
    console.error("   ❌ Error al hacer fetch a 127.0.0.1 /health:", err);
  }

  console.groupEnd();
})();
