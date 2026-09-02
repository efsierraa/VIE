# VIE — Vigilancia de Ingresos y Egresos

> **El control de acceso de tu edificio, en un escaneo.**  
> Una app gratuita, libre y hecha con el corazón: mi tío es guarda y sé lo que es anotar de noche, bajo la lluvia, en una libreta que se acaba de mojar.

---

## 1. El problema

En la mayoría de edificios residenciales, el control de acceso sigue siendo 100% manual:

- El guarda anota cada visitante en una **libreta física**: lenta, ilegible, fácil de perder.
- Cada ingreso implica **llamar al apartamento** y esperar que alguien conteste.
- **Cero trazabilidad**: ¿quién autorizó ese ingreso? ¿cuánto duró la visita? Nadie lo sabe con certeza.
- La información queda en papel que **nadie audita**, y la seguridad del edificio depende de la memoria y la letra del guarda de turno.

El resultado: riesgo de seguridad real, trabajo pesado e injusto para el guarda, y nula visibilidad para administración y consejo.

## 2. La solución

**VIE** digitaliza el control de acceso con **códigos QR de un solo uso**:

1. El **residente** genera un QR desde la app con los datos básicos de su visita.
2. Se lo comparte al visitante por **cualquier plataforma** — WhatsApp, Telegram, SMS, correo — como **imagen** o como **código de texto**.
3. El **guarda escanea** el QR en portería: en segundos verifica si está autorizado y registra el ingreso.
4. Cuando el visitante sale, el guarda hace un **segundo escaneo opcional que marca la salida** — así el edificio sabe exactamente cuánto duró cada visita.

El visitante **no instala nada**. Recibe el pase — imagen o código de texto — por el canal que prefiera y lo muestra en portería.

## 3. Cómo funciona, por rol

### Residente
- Genera un QR por cada visita desde su celular.
- El QR incluye datos básicos configurables: **nombre del visitante, asunto, identificación (opcional) y rol** (visitante, domiciliario, etc.).
- Comparte el pase por cualquier app de mensajería, como **imagen** o como **código de texto**. Sin llamadas, sin bajadas a portería, sin fotos de cédulas.

### Guarda
- **Escaneo de entrada**: la app le muestra de un vistazo si el visitante está autorizado, a qué torre y apartamento va, y con qué asunto.
- **Escaneo de salida (opcional, recomendado)**: marca la salida del visitante para tener control de la duración de la estancia.
- **Código de texto como respaldo**: si el visitante no puede mostrar la imagen, el guarda digita el código alfanumérico equivalente.
- El QR **es de un solo uso**: no se puede reutilizar ni reenviar para colarse.

### Visitante / domiciliario
- Recibe el pase — imagen o código de texto —, llega, lo muestra, entra.
- **Cero fricción**: no descarga la app, no se registra, no crea cuentas.

### Administración y consejo
- Son **dueños y supervisores de la base de datos de ingresos**: quién autorizó cada ingreso, nombre del visitante, torre, apartamento, hora de entrada y salida.
- Tienen el historial completo, consultable y auditable, en lugar de libretas físicas.

## 4. Objetivo · Propósito · Impacto

| | |
|---|---|
| **Objetivo** | Digitalizar y fortalecer el control de ingresos y egresos en edificios residenciales, con tecnología accesible para porterías de cualquier presupuesto. |
| **Propósito** | Un proyecto **social y open source** con dos motores: mejorar el portafolio profesional de quien lo desarrolla y, sobre todo, **hacerle la vida más fácil a los guardaes** — los primeros en servir y los últimos en ser escuchados. Esta app nació por mi tío, que es guarda. Es una app hecha con el corazón. |
| **Impacto** | - **Seguridad**: trazabilidad total de quién entra, quién autorizó y cuánto duró la visita.<br>- **Dignidad laboral**: menos carga manual para el guarda, menos error humano.<br>- **Comunidad**: residentes con control real sobre quién accede a su hogar.<br>- **Software libre**: cualquier edificio puede usarlo, adaptarlo y mejorarlo. Sin licencias, sin suscripciones, sin letra pequeña — y con una comunidad que corrige bugs y añade mejoras a velocidad que ningún proveedor cerrado puede igualar. |

## 5. Características del MVP

- Generación de **QR de un solo uso** desde la app del residente.
- Datos de visita: nombre, asunto, identificación opcional, rol (visitante, domiciliario).
- **Compartir sin ataduras**: el pase se envía por cualquier plataforma como **imagen (QR)** o **código de texto** digitable por el guarda.
- Escaneo del guarda: **validación de autorización** en segundos.
- **Registro de entrada y salida** (salida opcional) con cálculo de duración de visita.
- Historial de ingresos: visitante, autorizante, torre, apartamento, fecha y hora.
- Roles diferenciados: **solo residentes y personal de seguridad usan la app**; los visitantes solo reciben el QR.

## 6. Adopción y plan de contingencia

VIE no llega a imponerse: llega a **acompañar**.

- **Acuerdo con la administración**: la app se implementa solo con el visto bueno de administración y consejo, que además supervisan la base de datos de ingresos.
- **Periodo de acostumbración**: durante la transición, el guarda puede **digitar manualmente** todos los datos de quien ingresa si el visitante no trae QR o el residente no usa la app. Nadie queda por fuera.
- **Plan B garantizado**: si la app falla, se vuelve —sin drama— al método de siempre: llamar al apartamento y anotar. Cero costo, cero dependencia de un proveedor.
- **Mejora continua por la comunidad**: al ser gratuita y open source, VIE puede ser **rápidamente mejorada y sus bugs reparados por la comunidad**. Cualquier desarrollador puede reportar problemas, proponer soluciones y contribuir código — la app evoluciona al ritmo de quienes la usan, no al ritmo de un proveedor.

## 7. Privacidad y seguridad

- **Datos mínimos**: solo lo necesario para autorizar un ingreso. Nada de perfiles, publicidad ni venta de datos.
- **QR efímero**: un solo uso, sin reutilización posible.
- **Acceso controlado**: la base de datos de ingresos es administrada y supervisada exclusivamente por la administración y el consejo del edificio.
- **Open source = auditorable**: cualquier persona puede revisar el código y verificar qué hace con los datos. La transparencia es la mejor política de privacidad.

## 8. Roadmap futuro

Una vez consolidado el MVP, la misma lógica de códigos escaneables se extiende a:

- **Recepción de paquetes y documentos**: código de barras por paquete, pegado en portería; escaneo al entregar con comentario y/o **nota de voz** sobre a quién se entregó.
- **Biometría en portería**: si el celular de portería soporta huella, registrar la huella de quien recibe un paquete; o conectarse a un **lector profesional** externo.
- Reportes y estadísticas para administración y consejo.

## 9. Tecnología (visión breve)

- **Android nativo / PWA**: ligera, instalable o directo del navegador, pensada para los celulares económicos que suelen haber en portería.
- Arquitectura simple y mantenible por la comunidad, priorizando **funcionar sin fricción** sobre promesas de feature infinitas.

## 10. Llamado a la acción

VIE es **gratuita, libre y comunitaria**. Estamos buscando el **edificio piloto** donde nacer, crecer y demostrar que la seguridad residencial no necesita presupuestos gigantes: necesita buena tecnología, hecha por gente que conoce el problema de cerca.

**¿Tienes un edificio, una administración o un consejo dispuesto a probarlo? Hablemos.**

---

*VIE: porque quien cuida la puerta merece mejores herramientas.*
