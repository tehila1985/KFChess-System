# ארכיטקטורת KFChess

## תיאור כללי

KFChess הוא שחמט בזמן אמת — שני שחקנים זזים במקביל ללא תורות.
כל כלי נע בפיזיקה אמיתית עם זמן תנועה, וניצחון קיים רק בלכידת המלך.

---

## מבנה הפרויקט

```
chess/
├── main.py                              # Entry point — מעביר stdin ל-GameRunner
├── engine/
│   ├── config.py                        # כל ה-constants במקום אחד
│   ├── game_runner.py                   # פרסור קלט + בניית שכבות + הרצת פקודות
│   ├── game_engine.py                   # מתאם מרכזי בין כל השכבות
│   ├── models/
│   │   ├── position.py                  # (row, col) — כתובת תא
│   │   ├── piece.py                     # (color, type_code) — זהות כלי
│   │   ├── move.py                      # (src, dst) — בקשת תנועה
│   │   └── board.py                     # גריד + חסימת נתיב
│   ├── rules/
│   │   └── rule_engine.py               # אימות חוקיות תנועה (stateless)
│   └── arbiter/
│       └── real_time_arbiter.py         # ניהול תנועות בו-זמניות + התנגשויות
├── ui/
│   ├── interaction/                     # קלט לוגי ומיפוי קואורדינטות
│   │   ├── board_mapper.py              # פיקסל → משבצת
│   │   ├── controller.py                # לוגיקת שני-קליקים
│   │   └── controller_outcome.py        # התאמת תוצאת Controller ל-ActionOutcome
│   ├── composition/
│   │   └── container.py                 # חיווט תלותים לאפליקציית UI
│   ├── presentation/
│   │   └── text_renderer.py             # GameSnapshot → טקסט
│   ├── rendering/                       # שלבי ציור board/HUD
│   ├── animation/                       # שעון פריימים + אינטרפולציה
│   ├── ui_components/                   # פאנלים ותתי-רכיבי HUD
│   ├── state/                           # facade + events + observer
│   ├── resources/
│   │   └── asset_loader.py              # טעינה ועיבוד של assets
│   ├── runtime/
│   │   └── game_loop.py                 # לולאת runtime של OpenCV
│   ├── config/
│   │   ├── app_config.py                # קבועי runtime/layout/messages
│   │   └── ui_config.py                 # קונפיג UI גלובלי (חלון/skin/layout)
│   └── main.py                          # Entry point דק לשכבת UI
└── tests/
    ├── test_runner_scenarios.py         # E2E — מריץ GameRunner עם קלט טקסטואלי
    ├── test_game_engine.py
    ├── test_arbiter.py
    ├── test_rule_engine.py
    ├── test_models.py
    ├── test_ui.py
    └── test_integration_scenario.py
```

---

## שכבות הארכיטקטורה

### 1. Models — נתונים טהורים (`engine/models/`)

אובייקטים ללא לוגיקה, ללא state, frozen.

| קובץ | תפקיד |
|------|--------|
| `position.py` | כתובת תא (row, col) |
| `piece.py` | זהות כלי (color + type_code). `from_token('wK')` ← → `token` |
| `move.py` | בקשת תנועה (src → dst) |
| `board.py` | גריד של tokens. קריאה/כתיבה, גבולות, חסימת נתיב |

**למה נפרד:** שכבות עליונות יכולות לעבוד עם נתונים בלי לדעת כלום על UI או תזמון.

---

### 2. Config (`engine/config.py`)

כל ה-constants במקום אחד: צבעים, קודי כלים, מהירויות, ניקוד, גדלי UI.

**למה נפרד:** שינוי מהירות כלי = שינוי שורה אחת, בלי לגעת בלוגיקה.

---

### 3. RuleEngine — אימות חוקיות (`engine/rules/rule_engine.py`)

Stateless validator. מקבל `(board, move)` ומחזיר `MoveStatus`.

#### Strategy Pattern — MovementRule

כל סוג כלי מממש `MovementRule` בנפרד:

```
MovementRule (abstract)
├── KingRule    — צעד אחד בכל כיוון
├── RookRule    — קו ישר
├── BishopRule  — אלכסון
├── QueenRule   — Rook + Bishop
├── KnightRule  — L-shape, is_jumper=True (לא נחסם)
└── PawnRule    — קדימה/לכידה אלכסונית/כפול מהתחלה
```

סדר הבדיקות ב-`validate_move`:
1. גבולות לוח
2. קיום כלי במקור
3. יעד לא תפוס על ידי ידידותי
4. חוקיות גיאומטרית לפי סוג הכלי
5. חסימת נתיב (פרש פטור)

**למה נפרד:** הוספת כלי חדש = class אחד + שורה ב-`_RULES`. RuleEngine לא משתנה.

---

### 4. RealTimeArbiter — תנועות בו-זמניות (`engine/arbiter/real_time_arbiter.py`)

מנהל רשימת `ActiveMotion` ומפתור התנגשויות.

#### ActiveMotion

```
piece, src, dst, start_time, duration, is_jump
end_time = start_time + duration
```

- תנועה רגילה: הכלי נמחק מ-src ב-`start_motion`, מונח ב-dst ב-`_resolve`
- קפיצה (`is_jump=True`): הכלי נשאר על הלוח, יכול ללכוד מגיעים

#### `_resolve` — סדר פתרון

```
1. head-to-head: שני כלים שהחליפו מקומות — מי התחיל מאוחר מפסיד
2. קפיצות: כלי קופץ לוכד כלי אויב שמגיע לאותה משבצת
3. תנועות רגילות: הנח ביעד, לכוד מה שיש שם
```

#### `_route_conflicts`

חוסם תנועה אם כלי אחר כבר נע לאותה עמודה יעד מאותו כיוון.
מונע שני כלים על אותו נתיב בו-זמנית.

**למה נפרד מ-RuleEngine:** RuleEngine בודק חוקיות שחמט, Arbiter בודק פיזיקת זמן אמת.

---

### 5. GameEngine — מתאם מרכזי (`engine/game_engine.py`)

מחבר בין כל השכבות. לא מכיר UI, לא מכיר פיקסלים.

| מתודה | תפקיד |
|-------|--------|
| `request_move(src, dst)` | אימות + העברה ל-Arbiter |
| `request_jump(x, y)` | המרת פיקסל → משבצת + קפיצה |
| `tick(delta_ms)` | קידום זמן + טיפול בלכידות + קידום חיילים |
| `get_snapshot()` | תמונת מצב לצורך UI |
| `get_piece_at(pos)` | מחזיר כלי גם אם הוא בתנועה |

#### GameSnapshot

```python
grid           # גריד עם כלים בתנועה מוצגים ב-src שלהם
scores         # {w: int, b: int}
game_over      # bool
winner         # 'w' / 'b' / None
active_motions # tuple של MotionSummary
```

---

### 6. UI Layer (`ui/`)

שכבה דקה — לא מכירה כללי שחמט.

| מודול | תפקיד |
|------|--------|
| `interaction/board_mapper.py` | `(x, y)` פיקסל → `Position`. מחזיר None אם מחוץ ללוח |
| `interaction/controller.py` | שני-קליקים: קליק ראשון=בחירה, שני=תנועה. מחליף בחירה לכלי ידידותי |
| `interaction/controller_outcome.py` | מנרמל תוצאות click ל-`ActionOutcome` עבור ה-UI loop |
| `composition/container.py` | בונה `AppContainer` ומחבר Engine/Facade/Components |
| `presentation/text_renderer.py` | `GameSnapshot` → מחרוזת טקסט |
| `resources/asset_loader.py` | טעינת sprites/overlays, resize וקונפיג fps לפי state |
| `runtime/game_loop.py` | לולאת UI בפועל: input, tick, render, status |
| `config/app_config.py` | קבועי runtime/layout/messages בלי hard-coded בלוגיקה |
| `config/ui_config.py` | קונפיג UI קבוע משותף לשכבות |

**למה נפרד:** מאפשר להחליף renderer או input adapter בלי לגעת ב-GameEngine.

---

### 7. GameRunner (`engine/game_runner.py`)

Entry point לוגי — מחבר קלט טקסטואלי למנוע.

```
1. פרסור קלט → board_lines + commands
2. _validate_board → ERROR או None
3. בניית שכבות: Board → RuleEngine → Arbiter → GameEngine → Controller
4. הרצת פקודות: click / jump / wait / print
```

**למה נפרד מ-GameEngine:** Runner מכיר פורמט קלט/פלט, GameEngine לא.

---

## Data Flow — דוגמה מלאה

```
קלט: "click 50 50" + "click 150 150" + "wait 1000" + "print board"

1. GameRunner.run()
   └─ controller.on_click(50, 50)
      └─ BoardMapper.to_position(50, 50) → Position(0, 0)
      └─ Controller._src = Position(0, 0)  [בחירה]

2. controller.on_click(150, 150)
   └─ BoardMapper.to_position(150, 150) → Position(1, 1)
   └─ engine.request_move(Position(0,0), Position(1,1))
      └─ RuleEngine.validate_move() → MoveStatus.OK
      └─ Arbiter.start_motion(piece, src, dst, duration=1000)
         └─ board.set_piece(src, None)  [כלי נמחק מ-src]

3. engine.tick(1000)
   └─ Arbiter.advance_time(1000)
      └─ _resolve() → CompletedMotion
         └─ board.set_piece(dst, piece)  [כלי מונח ב-dst]

4. engine.get_snapshot() → GameSnapshot
   └─ TextRenderer.render_board_only() → הדפסה
```

---

## Design Patterns

| Pattern | מקום | מטרה |
|---------|------|-------|
| Strategy | `rule_engine.py` | MovementRule — כל כלי כלל נפרד |
| Snapshot | `game_engine.py` | GameSnapshot — UI קורא state בלי לשנות |
| Layered Architecture | כל הפרויקט | כל שכבה מכירה רק את שמתחתיה |

---

## הרצת טסטים

```bash
pytest tests/
```

כל שכבה בדוקה בנפרד. `test_runner_scenarios.py` הוא E2E — מריץ GameRunner עם קלט טקסטואלי ובודק פלט.

---

**Version:** 2.0 — משקף את המבנה האמיתי של הקוד
