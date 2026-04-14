# Timetabling — Gerador de Horários Escolar

Sistema de geração automática de horários escolares usando **Algoritmos Híbridos (CP + Local Search)**.

- **Fase 1 – CP-SAT** (OR-Tools): encontra uma solução viável satisfazendo todas as restrições rígidas (*hard constraints*).
- **Fase 2 – Local Search** (Hill Climbing): melhora a solução minimizando violações ponderadas de restrições flexíveis (*soft constraints*).

---

## Requisitos

| Ferramenta | Versão mínima |
|------------|---------------|
| Python     | 3.13          |
| uv         | 0.10+         |
| Docker     | 24+           |
| Docker Compose | v2        |

---

## Início Rápido

### 1. Clonar e configurar

```bash
git clone <repo-url> timetabling
cd timetabling
cp .env.example .env
```

### 2. Subir com Docker (recomendado)

```bash
docker compose up --build
```

O container `app` executa automaticamente o solver com os dados de exemplo em `data/input/`.  
Os CSVs são gerados em `data/output/`.

### 3. Rodar localmente (sem Docker)

```bash
# Instalar dependências
uv sync

# Certifique-se de ter um MySQL rodando e DATABASE_URL configurado no .env

# Executar
uv run python -m timetabling.main solve \
  --hard data/input/hard_blocks.json \
  --soft data/input/soft_blocks.json \
  --output data/output/

# Pular persistência no MySQL (modo offline)
uv run python -m timetabling.main solve --no-db
```

---

## Estrutura do Projeto

```
timetabling/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── migrations/
│   └── init.sql               ← Schema MySQL
├── docs/
│   └── ARCHITECTURE.md        ← Documentação técnica detalhada
├── data/
│   ├── input/
│   │   ├── hard_blocks.json   ← Definição do problema + restrições rígidas
│   │   └── soft_blocks.json   ← Restrições flexíveis com pesos
│   └── output/                ← CSVs gerados (um por turma)
└── src/timetabling/
    ├── main.py                ← CLI
    ├── config.py              ← Configuração via variáveis de ambiente
    ├── models/domain.py       ← Modelos Pydantic
    ├── db/
    │   ├── schema.py          ← ORM SQLAlchemy
    │   └── repository.py      ← Acesso ao banco
    ├── io/
    │   ├── json_loader.py     ← Carregamento e validação dos JSONs
    │   └── csv_exporter.py    ← Exportação CSV por turma
    └── solver/
        ├── cp_solver.py       ← Fase 1: CP-SAT
        ├── evaluator.py       ← Pontuação de soft constraints
        └── local_search.py    ← Fase 2: Hill Climbing
```

---

## Formato do JSON de Entrada

### `hard_blocks.json`

Define toda a estrutura do problema: escola, professores, turmas, matérias, requisitos e bloqueios rígidos.

```json
{
  "school": {
    "days": ["Segunda", "Terca", "Quarta", "Quinta", "Sexta"],
    "slots": [
      {"id": 1, "label": "07:00"},
      {"id": 2, "label": "08:00"},
      {"id": 5, "label": "13:00"}
    ]
  },
  "teachers": [
    {"id": "T1", "name": "Ana Paula", "subjects": ["MAT", "FIS"]}
  ],
  "classes": [
    {"id": "C1", "name": "1A", "level": "fundamental", "available_slots": [1, 2, 3, 4]},
    {"id": "C2", "name": "3A", "level": "medio",       "available_slots": [1, 2, 3, 4, 5, 6, 7, 8]}
  ],
  "subjects": [
    {"id": "MAT", "name": "Matematica"},
    {"id": "FIS", "name": "Fisica"}
  ],
  "requirements": [
    {"class_id": "C1", "subject_id": "MAT", "teacher_id": "T1", "hours_per_week": 4}
  ],
  "hard_blocks": [
    {"type": "teacher_unavailable", "teacher_id": "T1", "day": "Sexta", "slot": 1},
    {"type": "class_unavailable",   "class_id":   "C1", "day": "Sexta", "slot": 4}
  ]
}
```

**Campos de `hard_blocks`:**

| type | campos obrigatórios | descrição |
|------|---------------------|-----------|
| `teacher_unavailable` | `teacher_id`, `day`, `slot` | Professor indisponível naquele horário |
| `class_unavailable`   | `class_id`, `day`, `slot`   | Turma indisponível naquele horário |

### `soft_blocks.json`

Define preferências e penalidades com peso.

```json
{
  "soft_blocks": [
    {"type": "teacher_preferred_slot", "teacher_id": "T1", "day": "Segunda", "slot": 1, "weight": 5},
    {"type": "avoid_last_slot",        "class_id": "C1", "weight": 4},
    {"type": "avoid_teacher_gaps",     "teacher_id": "T1", "weight": 5},
    {"type": "subject_spread",         "class_id": "C1", "subject_id": "MAT", "weight": 3},
    {"type": "max_consecutive",        "class_id": "C2", "max_consecutive": 3, "weight": 5},
    {"type": "class_preferred_slot",   "class_id": "C1", "day": "Segunda", "slot": 1, "weight": 2}
  ]
}
```

**Tipos de `soft_blocks`:**

| type | campos | descrição |
|------|--------|-----------|
| `teacher_preferred_slot` | `teacher_id`, `day`, `slot`, `weight` | Penaliza se professor não estiver naquele slot |
| `class_preferred_slot`   | `class_id`, `day`, `slot`, `weight`   | Penaliza se turma não tiver aula naquele slot |
| `avoid_last_slot`        | `class_id`, `weight`                  | Penaliza aula no último slot do dia da turma |
| `avoid_teacher_gaps`     | `teacher_id`, `weight`                | Penaliza buracos no dia do professor |
| `subject_spread`         | `class_id`, `subject_id`, `weight`    | Penaliza aulas da mesma matéria no mesmo dia |
| `max_consecutive`        | `class_id`, `max_consecutive`, `weight` | Penaliza mais de N aulas consecutivas |

---

## Saída CSV

Um CSV por turma, em `data/output/<nome_turma>.csv`:

```
Slot,Label,Segunda,Terca,Quarta,Quinta,Sexta
1,07:00,Matematica - Ana Paula,,Portugues - Carlos Mendes,,
2,08:00,,Historia - Rodrigo Lima,,,
3,09:00,Biologia - Beatriz Costa,,,,
4,10:00,,Matematica - Ana Paula,,,
```

Turmas fundamental têm apenas linhas dos slots 1–4 (manhã).  
Turmas médio têm linhas dos slots 1–8 (manhã + tarde).

---

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DATABASE_URL` | `mysql+pymysql://app:apppass@localhost:3306/timetabling` | URL de conexão MySQL |
| `HARD_BLOCKS_PATH` | `data/input/hard_blocks.json` | Caminho do JSON de entrada |
| `SOFT_BLOCKS_PATH` | `data/input/soft_blocks.json` | Caminho dos soft blocks |
| `OUTPUT_DIR` | `data/output` | Diretório de saída dos CSVs |
| `CP_TIME_LIMIT_SECONDS` | `60` | Tempo máximo para o CP-SAT |
| `LS_MAX_ITERATIONS` | `5000` | Iterações máximas do Local Search |

---

## Documentação Técnica

Ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para detalhes sobre o modelo de domínio, algoritmo e decisões de design.
