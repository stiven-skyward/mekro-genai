# Cerebros de nube con tu propia clave (BYOK)

Lo local es el defecto y la identidad del proyecto. Esto es una alternativa **opt-in**
para quien quiera velocidad de nube y ponga su clave, su coste y su política.

## Configurar

Crea `~/.config/genai/claves.json` **con permisos 600** (nunca dentro del repositorio):

```json
{
  "gemini":    {"clave": "..."},
  "anthropic": {"clave": "...", "modelo": "claude-opus-5"},
  "openai":    {"clave": "..."},
  "deepseek":  {"clave": "..."},
  "kimi":      {"clave": "..."}
}
```

```bash
chmod 600 ~/.config/genai/claves.json
```

## Usar

```bash
genai tarea "arregla el bug" --cerebro nube:gemini
genai tarea "..." --cerebro nube:gemini/gemini-3.7-flash    # modelo explícito
genai tarea "..." --cerebro nube:anthropic/claude-opus-5
genai tarea "..." --cerebro nube:deepseek

# el banco también, y el registro deja constancia de que fue nube
python3 scripts/correr_banco.py --nivel n1 --cerebro nube:gemini
```

## Proveedores conocidos

| nombre | dialecto | modelo por defecto |
|---|---|---|
| `gemini` | nativo Gemini | `gemini-3.7-flash` |
| `anthropic` | Messages API | `claude-opus-5` |
| `openai` | chat/completions | `gpt-5.1` |
| `deepseek` | compatible OpenAI | `deepseek-chat` |
| `kimi` | compatible OpenAI (Moonshot) | `kimi-k2-turbo-preview` |
| `xai` | compatible OpenAI | `grok-4` |
| `groq` | compatible OpenAI | `llama-3.3-70b-versatile` |
| `openrouter` | compatible OpenAI | `openai/gpt-5.1` |

**Cualquier otro endpoint compatible con OpenAI** funciona sin tocar el código: añade
`{"url": "https://...", "dialecto": "openai", "modelo": "...", "clave": "..."}` con el
nombre que quieras.

## Cómo funciona por dentro

Tres formas de API cubren el mercado, y el adaptador habla las tres con `urllib` de la
biblioteca estándar — ni un SDK nuevo, porque la dependencia única
(`llama-cpp-python`) es parte de lo que hace este proyecto instalable en hardware
modesto:

- **Gemini** — `contents[]` + `functionDeclarations`; el sistema va en
  `systemInstruction`. Gemini 3.x exige devolver el `thoughtSignature` de cada
  `functionCall` (responde 400 si falta): el adaptador lo guarda por id de llamada y lo
  reinyecta.
- **Anthropic** — `x-api-key` + `anthropic-version`; herramientas con `input_schema`,
  llamadas como bloques `tool_use` y observaciones como `tool_result`.
- **OpenAI y compatibles** — `tool_calls` con argumentos serializados; las firmas de
  herramientas del arnés ya vienen en este dialecto y pasan tal cual.

**Las llamadas a herramientas son nativas, no Hermes.** El cerebro local emite Hermes
en texto porque es lo que Qwen trae entrenado; los modelos de nube tienen llamada a
funciones nativa y es mucho más fiable. El bucle, los permisos y el banco no notan la
diferencia.

## Las dos reglas que no se negocian

1. **Una carrera de nube nunca cuenta como cifra local.** El cerebro se registra como
   `nube:proveedor/modelo`; M0 y M2 se declararon con el cerebro local y ahí siguen.
2. **Tu clave es tuya**: fuera del repositorio, con permisos 600, y jamás en un
   registro, un log o un nombre. Si una clave se te escapa a un sitio compartido,
   rótala — es más barato que cualquier auditoría.

## Coste y velocidad, medidos

`n1/anadir`, misma tarea y mismo verificador determinista:

| cerebro | reloj | tokens |
|---|---|---|
| local (Qwen 2,8 bits, CPU) | 757-969 s | 493 |
| `nube:gemini/gemini-3.7-flash` | **25,6 s** | 339 |

~30× de reloj. Lo que compras con la nube es tiempo; lo que pagas es dependencia de un
tercero y el coste por token. Por eso ambos modos existen y el local es el defecto.
