<!-- synced-from: 489dedb3f52407ccc52186715cd3d51a74aaad5a -->
# typedout

**Español** · [English](README.md)

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![tests](https://img.shields.io/badge/tests-100%20passing-brightgreen.svg)](tests/)

**Salida estructurada fiable de OpenAI y Anthropic, con una interfaz de proveedor para añadir otros.** Defines un esquema y recuperas un objeto validado — con reparación tolerante de JSON, reintentos que aprenden del error y un proveedor simulado que funciona sin red. No hace falta clave de API para probarlo.

```python
from pydantic import BaseModel
from typedout import TypedOut, MockProvider

class Persona(BaseModel):
    nombre: str
    edad: int
    email: str

llm = TypedOut(MockProvider(script=["invalid", "valid"]))
persona = llm.extract(Persona, "Ada Lovelace, 36, ada@example.com")
```

> **Nota sobre el idioma.** Este README está en las dos lenguas. El resto de la documentación y los comentarios del código están en inglés.

---

## Por qué

Sacar datos *válidos y tipados* de un modelo de lenguaje es más difícil de lo que parece. Los modelos envuelven el JSON en vallas ```` ```json ````, meten un «Claro, aquí lo tienes» delante, escriben `True`/`None` de Python, dejan comas colgando, usan comillas simples, o simplemente se cortan a mitad de objeto al llegar al límite de tokens. `typedout` se encarga de todo eso detrás de una API pequeña:

- **Reparación tolerante de JSON** — un escáner de una pasada, consciente de las cadenas, convierte *casi*-JSON en JSON estricto (sin `eval`, sin red).
- **Validación de esquema** — modelos de pydantic *o* diccionarios de JSON Schema en crudo.
- **Reintentos que aprenden del error** — cuando la validación falla, los errores concretos se le devuelven al modelo y lo intenta otra vez.
- **Agnóstico de proveedor** — Anthropic, OpenAI o el tuyo; incluye un **`MockProvider`** determinista para que las pruebas y las demos funcionen sin salir a la red.
- **Extras** — **streaming** de objetos parciales, **conteo de tokens y coste**, y un decorador **`@extract`** que convierte cualquier función en un extractor tipado.

## Instalación

```bash
pip install typedout-py                # básico (sólo pydantic)
pip install "typedout-py[anthropic]"   # + SDK de Anthropic
pip install "typedout-py[openai]"      # + SDK de OpenAI
```

**Se instala `typedout-py` y se importa `typedout`.** El nombre de distribución lleva el sufijo `-py`; el paquete que importas, no:

```python
from typedout import TypedOut
```

Necesita Python 3.10+. La única dependencia dura es `pydantic>=2`.

> **Renombrado desde `structllm` el 4-sep-2026.** El nombre de distribución `structllm` lo tiene en PyPI otro proyecto que hace lo mismo — *«Universal Python library for Structured Outputs with any LLM provider»* — así que este paquete nunca se podría haber publicado con ese nombre, y quien lo buscara habría encontrado la otra librería. La URL de GitHub del nombre viejo sigue redirigiendo aquí.
>
> **Y por qué el sufijo `-py`.** PyPI también rechaza el nombre `typedout` a secas: normaliza y elimina `-`, `_` y `.` antes de comparar, así que `typedout` choca con un proyecto ajeno llamado `typed-out`. Renombrar la librería por tercera vez habría costado más de lo que vale, así que la distribución es `typedout-py` y el import sigue siendo `typedout` — la misma separación que `beautifulsoup4`/`bs4` o `pillow`/`PIL`.

## Uso

### 1. Extraer un objeto tipado

```python
from pydantic import BaseModel, Field
from typedout import TypedOut
from typedout import AnthropicProvider          # o OpenAIProvider, o el tuyo

class Factura(BaseModel):
    numero: str
    total: float = Field(ge=0)
    moneda: str

llm = TypedOut(AnthropicProvider())  # por defecto claude-opus-5
factura = llm.extract(Factura, "Factura INV-2043, total 1.299,00 EUR, a 30 días")
```

Por defecto usa **`claude-opus-5`** — el modelo más capaz, elegido porque el bucle de reintentos le devuelve los errores de validación, y un modelo que acierta a la primera suele salir más barato **por extracción correcta** que uno más barato que necesita tres intentos. No es el más barato por token: al escribir esto son 5 $ / 25 $ por millón de tokens de entrada / salida, frente a 2 $ / 10 $ de `claude-sonnet-5`. Con `model=` eliges otro, y `llm.last_usage` te dice lo que costó de verdad la llamada.

El esquema se inyecta en el prompt automáticamente. Si la respuesta del modelo no parsea o no valida, `typedout` la repara, y —si aun así falla— vuelve a preguntar con los errores exactos (hasta `max_retries`, por defecto 2).

### 2. El motor de reparación, por separado

`repair_json` vale por sí solo. Estas son **salidas reales** de la librería:

```python
from typedout import repair_json

repair_json("```json\n{'name': 'Ada', 'age': 36,}\n```")
# -> {"name":"Ada","age":36}

repair_json('{"name": "Ada", "age": 36, "email": "ada@exampl')     # cortado
# -> {"name":"Ada","age":36,"email":"ada@exampl"}

repair_json("{name: 'Ada', active: True, mgr: None}")              # cosas de JS/Python
# -> {"name":"Ada","active":true,"mgr":null}

repair_json('Sure! Here you go:\n{"score": 9.5}\nHope that helps!') # prosa alrededor
# -> {"score":9.5}
```

| Arregla | Entra → sale |
| --- | --- |
| Vallas de markdown | ```` ```json {...} ``` ```` → `{...}` |
| Prosa alrededor | `Here you go: {...} thanks!` → `{...}` |
| Comas colgando | `[1, 2, 3,]` → `[1, 2, 3]` |
| Comillas simples | `{'a': 'b'}` → `{"a": "b"}` |
| Claves sin comillas | `{a: 1}` → `{"a": 1}` |
| Literales de Python | `True / False / None` → `true / false / null` |
| Comentarios `//` y `/* */` | se eliminan |
| Salida cortada | `{"a": [1, 2` → `{"a": [1, 2]}` |

### 3. `@extract` — un extractor tipado en tres líneas

```python
from typedout import extract, MockProvider

@extract(Persona, provider=MockProvider(script=["valid"]))
def parsea_persona(texto: str) -> Persona:
    return f"Extrae la persona descrita aquí:\n{texto}"
```

La función sólo construye el prompt; el decorador ejecuta la extracción y devuelve el objeto validado del tipo declarado.

### 4. Recibir el objeto parcial mientras se rellena

```python
llm = TypedOut(MockProvider(script=["valid"], chunk_size=8))
for parcial in llm.stream(Persona, "Ada Lovelace, 36, ada@example.com"):
    print(parcial)
print(repr(llm.last_result))   # Persona ya validada
```

El objeto se materializa campo a campo, incluso desde un flujo recibido a medias.

> `AnthropicProvider` y `OpenAIProvider` todavía no implementan streaming de tokens; con ellos `stream()` emite una sola instantánea con el objeto completo. Sobrescribe `Provider.stream()` en tu propio proveedor para tener instantáneas progresivas.

### 5. Contar tokens y coste

```python
llm.extract(Factura, "...")
print(llm.last_usage)     # esta llamada, reintentos incluidos
print(llm.total_usage)    # acumulado de la sesión
```

Los precios son configurables (`register_price(...)`) y por defecto son valores ilustrativos — aquí nada te cobra ni sale a la red.

### 6. JSON Schema en crudo, sin pydantic

Le pasas un diccionario normal y recuperas otro validado, comprobado por el validador ligero incorporado (`type`, `required`, `enum`, límites, `anyOf`, `$ref`…):

```python
esquema = {
    "type": "object",
    "properties": {"id": {"type": "integer"}, "prioridad": {"enum": ["baja", "alta"]}},
    "required": ["id"],
}
llm.extract(esquema, "ticket 7, prioridad alta")   # -> {"id": 7, "prioridad": "alta"}
```

## Cómo funciona

```
prompt ─▶ Provider.complete ─▶ repair(texto) ─▶ validate(esquema) ─▶ objeto tipado
                  ▲                                     │
                  └──── vuelve a preguntar con errores ◀─┘  (hasta max_retries)
```

1. **Prompt** — el JSON Schema se incrusta en un prompt de sistema que pide un único objeto JSON.
2. **Reparación** — `repair.py` recorre la respuesta carácter a carácter. Las cadenas se recodifican con `json.dumps` (así su contenido nunca se corrompe); las llaves sin cerrar se cierran; se para en el primer valor completo de nivel superior e ignora la prosa que venga detrás.
3. **Validación** — pydantic (instancia tipada) o `jsonschema_lite` (diccionario).
4. **Reintento** — si falla, se añaden la respuesta mala del asistente y una corrección precisa («campo `edad`: debería ser un entero válido»), y el modelo lo intenta otra vez.

Cada capa es independiente: puedes usar `repair_json` a secas, cambiar el proveedor, o mover todo sin red con `MockProvider` — que sabe sintetizar respuestas válidas contra el esquema (respeta `type`, `enum`, límites numéricos, `minLength`/`maxLength` y los `format` habituales; un `pattern` no lo sintetiza) o producir a propósito respuestas **con vallas**, **laxas**, **cortadas** o **inválidas** para ejercitar los caminos de reparación y reintento.

## Pruebas

```bash
pip install -e ".[dev]"
pytest                    # 100 pruebas, todas sin red
python examples/quickstart.py
```

La batería cubre el escáner de reparación (vallas, comentarios, truncado, unicode, anidamiento sucio), el validador de JSON Schema, el bucle de reintentos, el streaming, las cuentas de coste y el mapeo de peticiones a Anthropic y OpenAI (con clientes falsos inyectados — sin SDKs y sin claves).

## Parte del ecosistema ferinazumaDEV

`typedout` es una de un conjunto de herramientas pequeñas y concretas de ferinazumaDEV para construir con modelos de lenguaje de forma fiable — aquí, convertir la salida libre de un modelo en datos validados contra esquema de los que te puedes fiar. Proyectos relacionados:

- [The GEO Handbook](https://github.com/ferinazumaDEV/generative-engine-optimization-handbook) — la referencia abierta sobre conseguir que los motores de respuesta de IA te citen (ChatGPT, Perplexity, Google AI Overviews, Gemini, Copilot).
- [notebooklm-kb-system](https://github.com/ferinazumaDEV/notebooklm-kb-system) — un «segundo cerebro» eficiente en tokens para agentes de IA: memoria local, cuadernos de NotebookLM y enrutado de conocimiento.
- [politeclient](https://github.com/ferinazumaDEV/politeclient) — un cliente HTTP educado para Python: reintentos con espera, límite de ritmo por host y caché — útil para hablar con las APIs de los proveedores de modelos.
- [scaffld](https://github.com/ferinazumaDEV/scaffld) — genera proyectos Python completos (pruebas, CI, pre-commit, licencia) desde plantillas.
- Web y publicaciones: [zentimes.es](https://zentimes.es).

De [ferinazumaDEV](https://github.com/ferinazumaDEV).

## Licencia

MIT — ver [LICENSE](LICENSE).

---

*Hecho por Fernando Aporta Franco ([@ferinazumaDEV](https://github.com/ferinazumaDEV)).*
