import { useState, useMemo, useCallback, useEffect } from "react";

// ============================================================
// CONSTANTS
// ============================================================

const SIGNS = [
  { name: "Овен", sym: "♈", el: "fire" },
  { name: "Телец", sym: "♉", el: "earth" },
  { name: "Близнецы", sym: "♊", el: "air" },
  { name: "Рак", sym: "♋", el: "water" },
  { name: "Лев", sym: "♌", el: "fire" },
  { name: "Дева", sym: "♍", el: "earth" },
  { name: "Весы", sym: "♎", el: "air" },
  { name: "Скорпион", sym: "♏", el: "water" },
  { name: "Стрелец", sym: "♐", el: "fire" },
  { name: "Козерог", sym: "♑", el: "earth" },
  { name: "Водолей", sym: "♒", el: "air" },
  { name: "Рыбы", sym: "♓", el: "water" },
];

const ELEMENT_COLORS = {
  fire: "#e85d3a",
  earth: "#6baa3d",
  air: "#4da6d9",
  water: "#8b7ec8",
};

const PLANET_SYMBOLS = {
  "Солнце": "☉", "Луна": "☽", "Меркурий": "☿", "Венера": "♀",
  "Марс": "♂", "Юпитер": "♃", "Сатурн": "♄", "Уран": "♅",
  "Нептун": "♆", "Плутон": "♇", "Сев.Узел": "☊", "Юж.Узел": "☋",
  "Лилит": "⚸", "Селена": "⚜", "Хирон": "⚷",
  "Фортуна": "⊕", "Вертекс": "Vx",
};

const PLANET_COLORS = {
  "Солнце": "#f0c040", "Луна": "#c0c0d0", "Меркурий": "#80b0d0",
  "Венера": "#d08080", "Марс": "#e05040", "Юпитер": "#d09040",
  "Сатурн": "#808060", "Уран": "#40b0b0", "Нептун": "#6080c0",
  "Плутон": "#a06080", "Сев.Узел": "#90a090", "Юж.Узел": "#708070",
  "Лилит": "#706070", "Селена": "#b0c8a0", "Хирон": "#a09060",
  "Фортуна": "#c0a050", "Вертекс": "#6080a0",
};

// Vlad's natal data (pre-calculated)
const VLAD_NATAL = {
  name: "Влад",
  date: "30.01.1961",
  time: "20:56:40",
  tz: "GMT+6",
  lat: 54.42985,
  lon: 70.34136,
  place: "с. Советское, СКО",
  isDay: false,
  angles: {
    ASC: { abs: 162.4627, sign: 5, deg: 12, min: 27, sec: 45.6 },
    MC: { abs: 65.9977, sign: 2, deg: 5, min: 59, sec: 51.5 },
    DSC: { abs: 342.4627, sign: 11, deg: 12, min: 27, sec: 45.6 },
    IC: { abs: 245.9977, sign: 8, deg: 5, min: 59, sec: 51.5 },
  },
  planets: [
    { name: "Солнце", abs: 310.501682, sign: 10, deg: 10, min: 30, sec: 6.05, house: 5, housePart: 3, retro: false },
    { name: "Луна", abs: 117.960898, sign: 3, deg: 27, min: 57, sec: 39.23, house: 11, housePart: 2, retro: false },
    { name: "Меркурий", abs: 326.589719, sign: 10, deg: 26, min: 35, sec: 22.99, house: 6, housePart: 2, retro: false },
    { name: "Венера", abs: 357.437064, sign: 11, deg: 27, min: 26, sec: 13.43, house: 7, housePart: 3, retro: false },
    { name: "Марс", abs: 90.262719, sign: 3, deg: 0, min: 15, sec: 45.79, house: 10, housePart: 2, retro: true },
    { name: "Юпитер", abs: 290.938790, sign: 9, deg: 20, min: 56, sec: 19.64, house: 5, housePart: 1, retro: false },
    { name: "Сатурн", abs: 293.066024, sign: 9, deg: 23, min: 3, sec: 57.68, house: 5, housePart: 1, retro: false },
    { name: "Уран", abs: 144.322883, sign: 4, deg: 24, min: 19, sec: 22.38, house: 12, housePart: 1, retro: true },
    { name: "Нептун", abs: 221.276553, sign: 7, deg: 11, min: 16, sec: 35.59, house: 3, housePart: 1, retro: false },
    { name: "Плутон", abs: 157.501591, sign: 5, deg: 7, min: 30, sec: 5.73, house: 12, housePart: 3, retro: true },
    { name: "Сев.Узел", abs: 156.332765, sign: 5, deg: 6, min: 19, sec: 57.96, house: 12, housePart: 3, retro: true },
    { name: "Лилит", abs: 119.875132, sign: 3, deg: 29, min: 52, sec: 30.47, house: 11, housePart: 2, retro: false },
    { name: "Селена", abs: 40.7536, sign: 1, deg: 10, min: 45, sec: 13.0, house: 9, housePart: 1, retro: false },
    { name: "Хирон", abs: 330.6011, sign: 11, deg: 0, min: 36, sec: 4.0, house: 7, housePart: 1, retro: false },
    { name: "Юж.Узел", abs: 336.3328, sign: 11, deg: 6, min: 19, sec: 58.0, house: 7, housePart: 2, retro: true },
    { name: "Фортуна", abs: 355.0035, sign: 11, deg: 25, min: 0, sec: 12.6, house: 7, housePart: 3, retro: false },
    { name: "Вертекс", abs: 311.1747, sign: 10, deg: 21, min: 10, sec: 29.0, house: 6, housePart: 1, retro: false },
  ],
  houses: [
    { num: 1, cusp: 162.4627, sign: 5, ruler: "Меркурий" },
    { num: 2, cusp: 183.1907, sign: 6, ruler: "Венера" },
    { num: 3, cusp: 210.6219, sign: 7, ruler: "Плутон" },
    { num: 4, cusp: 245.9977, sign: 8, ruler: "Юпитер" },
    { num: 5, cusp: 284.7345, sign: 9, ruler: "Сатурн" },
    { num: 6, cusp: 317.1027, sign: 10, ruler: "Уран" },
    { num: 7, cusp: 342.4627, sign: 11, ruler: "Нептун" },
    { num: 8, cusp: 3.1907, sign: 0, ruler: "Марс" },
    { num: 9, cusp: 30.6219, sign: 1, ruler: "Венера" },
    { num: 10, cusp: 65.9977, sign: 2, ruler: "Меркурий" },
    { num: 11, cusp: 104.7345, sign: 3, ruler: "Луна" },
    { num: 12, cusp: 137.1027, sign: 4, ruler: "Солнце" },
  ],
};

// ============================================================
// MICRO CASCADE (JS port)
// ============================================================

function microCascade(minutes, seconds, levels = 7) {
  let totalArcsec = minutes * 60 + seconds;
  let segment = 3600;
  const results = [];

  for (let level = 1; level <= levels; level++) {
    segment = segment / 12;
    let signIndex = Math.floor(totalArcsec / segment);
    if (signIndex >= 12) signIndex = 11;
    const remainder = totalArcsec - signIndex * segment;
    const degree = (remainder / segment) * 30;
    const degInt = Math.floor(degree);
    const degMin = Math.floor((degree - degInt) * 60);

    results.push({
      level,
      signIndex,
      sign: SIGNS[signIndex],
      degree: Math.round(degree * 10000) / 10000,
      degInt,
      degMin,
      sabian: degInt + 1,
      segmentSize: segment,
    });

    totalArcsec = remainder;
  }
  return results;
}

// ============================================================
// FORMAT HELPERS
// ============================================================

function fmtPos(deg, min, sec) {
  return `${deg}°${String(min).padStart(2, "0")}'${sec !== undefined ? String(Math.floor(sec)).padStart(2, "0") + '"' : ""}`;
}

function fmtSize(arcsec) {
  if (arcsec >= 60) return `${(arcsec / 60).toFixed(2)}'`;
  if (arcsec >= 1) return `${arcsec.toFixed(3)}"`;
  if (arcsec >= 0.001) return `${(arcsec * 1000).toFixed(2)} mas`;
  return `${(arcsec * 1e6).toFixed(2)} μas`;
}

// ============================================================
// STYLES
// ============================================================

const S = {
  app: {
    background: "#0d0f1a",
    color: "#d0d0d8",
    minHeight: "100vh",
    fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace",
    fontSize: "12px",
    padding: "0",
  },
  header: {
    background: "#141628",
    borderBottom: "1px solid #2a2d42",
    padding: "12px 16px",
  },
  title: {
    fontSize: "15px",
    fontWeight: "600",
    color: "#e0e0e8",
    marginBottom: "8px",
    letterSpacing: "1px",
  },
  inputRow: {
    display: "flex",
    gap: "8px",
    flexWrap: "wrap",
    alignItems: "center",
    marginBottom: "6px",
  },
  label: {
    color: "#7078a0",
    fontSize: "10px",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
  },
  input: {
    background: "#1a1d30",
    border: "1px solid #2a2d42",
    color: "#d0d0d8",
    padding: "4px 8px",
    borderRadius: "3px",
    fontSize: "12px",
    fontFamily: "inherit",
    width: "70px",
  },
  inputWide: {
    width: "140px",
  },
  select: {
    background: "#1a1d30",
    border: "1px solid #2a2d42",
    color: "#d0d0d8",
    padding: "4px 6px",
    borderRadius: "3px",
    fontSize: "12px",
    fontFamily: "inherit",
  },
  btn: {
    background: "#2a3a5c",
    border: "1px solid #3a4a6c",
    color: "#c0c8e0",
    padding: "4px 12px",
    borderRadius: "3px",
    fontSize: "11px",
    cursor: "pointer",
    fontFamily: "inherit",
  },
  btnActive: {
    background: "#3a5a8c",
    borderColor: "#5a7aac",
    color: "#e0e8ff",
  },
  body: {
    display: "flex",
    flexDirection: "column",
    gap: "0",
  },
  chartArea: {
    width: "100%",
    padding: "8px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "80vh",
    borderBottom: "1px solid #2a2d42",
  },
  tableArea: {
    width: "100%",
    padding: "0",
  },
  sectionTitle: {
    padding: "6px 12px",
    background: "#181a2c",
    borderBottom: "1px solid #2a2d42",
    fontSize: "11px",
    fontWeight: "600",
    color: "#8890b0",
    textTransform: "uppercase",
    letterSpacing: "1px",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
  },
  th: {
    padding: "4px 8px",
    textAlign: "left",
    borderBottom: "1px solid #2a2d42",
    color: "#606888",
    fontSize: "10px",
    textTransform: "uppercase",
    fontWeight: "400",
  },
  td: {
    padding: "4px 8px",
    borderBottom: "1px solid #1a1d2a",
    fontSize: "12px",
    cursor: "pointer",
  },
  tdHover: {
    background: "#1a2040",
  },
  planetSym: {
    fontSize: "14px",
    width: "20px",
    display: "inline-block",
  },
  retro: {
    color: "#e05040",
    fontSize: "10px",
    marginLeft: "2px",
  },
  cascadePanel: {
    borderTop: "2px solid #2a3a5c",
    background: "#0f1120",
  },
  cascadeLevel: {
    display: "flex",
    alignItems: "center",
    padding: "4px 12px",
    borderBottom: "1px solid #1a1d2a",
    gap: "8px",
  },
  levelNum: {
    width: "24px",
    color: "#5060a0",
    fontSize: "10px",
    fontWeight: "600",
  },
  levelSign: {
    width: "24px",
    fontSize: "16px",
    textAlign: "center",
  },
  levelName: {
    width: "70px",
    fontSize: "11px",
  },
  levelDeg: {
    width: "60px",
    fontSize: "11px",
    color: "#a0a8c0",
  },
  levelSab: {
    width: "40px",
    fontSize: "10px",
    color: "#6068a0",
  },
  levelSize: {
    fontSize: "10px",
    color: "#4a5070",
  },
  separator: {
    borderTop: "1px solid #2a2d42",
    margin: "0",
  },
  modeTab: {
    display: "inline-block",
    padding: "3px 10px",
    fontSize: "10px",
    cursor: "pointer",
    borderBottom: "2px solid transparent",
    color: "#6068a0",
    marginRight: "4px",
  },
  modeTabActive: {
    borderBottomColor: "#5a7aac",
    color: "#c0c8e0",
  },
};

// ============================================================
// COMPONENTS
// ============================================================

function InputPanel({ data, setData, layers, setLayers, timerOn, setTimerOn, clockStr, dateStr, theme, setTheme }) {
  const toggleLayer = (layer) => setLayers({ ...layers, [layer]: !layers[layer] });
  const layerBtn = (key, label, color) => ({
    ...S.btn,
    padding: "3px 10px",
    fontSize: "10px",
    borderLeft: `3px solid ${layers[key] ? color : "#2a2d42"}`,
    background: layers[key] ? `${color}15` : "#1a1d30",
    color: layers[key] ? color : "#5060a0",
  });

  return (
    <div style={S.header}>
      <div style={{
        fontSize: "20px",
        fontWeight: "600",
        color: "#f0c040",
        letterSpacing: "3px",
        textAlign: "center",
        padding: "8px 0 6px",
        textShadow: "0 0 20px rgba(240,192,64,0.3)",
      }}>КВАНТАРЕОН — АСТРО-ФРАКТАЛ</div>

      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "12px", marginBottom: "8px", flexWrap: "wrap" }}>

        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: "6px",
            padding: "3px 10px",
            background: timerOn ? "#1a2a1a" : "#1a1d30",
            border: `1px solid ${timerOn ? "#2a5a2a" : "#2a2d42"}`,
            borderRadius: "3px",
            cursor: "pointer",
          }} onClick={() => setTimerOn(!timerOn)}>
            <span style={{ fontSize: "10px", color: timerOn ? "#50c050" : "#5060a0" }}>
              {timerOn ? "⏱ LIVE" : "⏱ OFF"}
            </span>
            <span style={{
              fontSize: "14px",
              fontWeight: "600",
              color: timerOn ? "#50e050" : "#4a5070",
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: "1px",
            }}>
              {clockStr}
            </span>
            <span style={{ fontSize: "10px", color: "#5060a0" }}>{dateStr}</span>
          </div>

          <div style={{
            padding: "3px 10px",
            background: "#1a1d30",
            border: "1px solid #2a2d42",
            borderRadius: "3px",
            cursor: "pointer",
            fontSize: "10px",
            color: theme === "dark-high-contrast" ? "#a0a8c0" : "#f0c040",
          }} onClick={() => setTheme(theme === "dark-high-contrast" ? "classic" : "dark-high-contrast")}>
            {theme === "dark-high-contrast" ? "🌙 Тёмная" : "☀ Светлая"}
          </div>

          <div style={{ width: "1px", height: "20px", background: "#2a2d42" }} />

          <span style={{ fontSize: "10px", color: "#5060a0" }}>СЛОИ:</span>
          <button style={layerBtn("natal", "Натал", "#4da6d9")} onClick={() => toggleLayer("natal")}>
            ● Натал
          </button>
          <button style={layerBtn("transit", "Транзит", "#e85d3a")} onClick={() => toggleLayer("transit")}>
            ● Транзит
          </button>
          <button style={layerBtn("horary", "Хорар", "#8b7ec8")} onClick={() => toggleLayer("horary")}>
            ● Хорар (ASC)
          </button>
          <button style={layerBtn("matrix", "Матрица", "#50c050")} onClick={() => toggleLayer("matrix")}>
            ● Матрица
          </button>
        </div>
      </div>

      <div style={S.inputRow}>
        <span style={S.label}>Имя</span>
        <input
          style={{ ...S.input, width: "100px" }}
          value={data.name}
          onChange={(e) => setData({ ...data, name: e.target.value })}
        />
        <span style={S.label}>Дата</span>
        <input style={S.input} value={data.date} onChange={(e) => setData({ ...data, date: e.target.value })} />
        <span style={S.label}>Время</span>
        <input style={S.input} value={data.time} onChange={(e) => setData({ ...data, time: e.target.value })} />
        <span style={S.label}>GMT</span>
        <input style={{ ...S.input, width: "40px" }} value={data.tz} onChange={(e) => setData({ ...data, tz: e.target.value })} />

        <div style={{ width: "1px", height: "20px", background: "#2a2d42", margin: "0 4px" }} />

        <span style={S.label}>Место</span>
        <input
          style={{ ...S.input, ...S.inputWide }}
          value={data.place}
          onChange={(e) => setData({ ...data, place: e.target.value })}
        />
      </div>

      <div style={S.inputRow}>
        <span style={S.label}>Lat</span>
        <input style={{ ...S.input, width: "90px" }} value={data.lat} onChange={(e) => setData({ ...data, lat: e.target.value })} />
        <span style={S.label}>Lon</span>
        <input style={{ ...S.input, width: "90px" }} value={data.lon} onChange={(e) => setData({ ...data, lon: e.target.value })} />

        <div style={{ width: "1px", height: "20px", background: "#2a2d42", margin: "0 4px" }} />

        <span style={S.label}>ASC°</span>
        <input style={{ ...S.input, width: "40px" }} value={data.ascDeg || ""} placeholder="—" onChange={(e) => setData({ ...data, ascDeg: e.target.value })} />
        <span style={S.label}>'</span>
        <input style={{ ...S.input, width: "35px" }} value={data.ascMin || ""} placeholder="—" onChange={(e) => setData({ ...data, ascMin: e.target.value })} />
        <span style={S.label}>Знак</span>
        <select style={S.select} value={data.ascSign || ""} onChange={(e) => setData({ ...data, ascSign: e.target.value })}>
          <option value="">—</option>
          {SIGNS.map((s, i) => (
            <option key={i} value={i}>{s.sym} {s.name}</option>
          ))}
        </select>

        <div style={{ width: "1px", height: "20px", background: "#2a2d42", margin: "0 4px" }} />

        <span style={S.label}>Задача</span>
        <select style={{ ...S.select, width: "150px" }} value={data.task || "natal"} onChange={(e) => setData({ ...data, task: e.target.value })}>
          <option value="natal">Натальная карта</option>
          <option value="micro">Микро-циклы</option>
          <option value="horary">Хорар (ASC)</option>
          <option value="fractal">Фрактальный расклад</option>
        </select>

        <button style={{ ...S.btn, padding: "4px 16px", fontWeight: "600" }}>
          Рассчитать
        </button>
      </div>
    </div>
  );
}

function PlanetTable({ planets, angles, houses, selected, onSelect }) {
  return (
    <div>
      <div style={S.sectionTitle}>Углы</div>
      <table style={S.table}>
        <tbody>
          {Object.entries(angles).map(([name, a]) => (
            <tr key={name}>
              <td style={{ ...S.td, fontWeight: "600", color: "#a0a8d0" }}>{name}</td>
              <td style={{ ...S.td, color: ELEMENT_COLORS[SIGNS[a.sign].el] }}>
                {SIGNS[a.sign].sym}
              </td>
              <td style={S.td}>{fmtPos(a.deg, a.min, a.sec)}</td>
              <td style={{ ...S.td, color: "#6068a0" }}>{SIGNS[a.sign].name}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={S.sectionTitle}>Планеты</div>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}></th>
            <th style={S.th}>Планета</th>
            <th style={S.th}></th>
            <th style={S.th}>Позиция</th>
            <th style={S.th}>Знак</th>
            <th style={S.th}>Дом</th>
          </tr>
        </thead>
        <tbody>
          {planets.map((p) => {
            const isSelected = selected === p.name;
            const color = PLANET_COLORS[p.name] || "#d0d0d8";
            return (
              <tr
                key={p.name}
                onClick={() => onSelect(p.name)}
                style={{
                  background: isSelected ? "#1a2040" : "transparent",
                  cursor: "pointer",
                }}
              >
                <td style={S.td}>
                  <span style={{ ...S.planetSym, color }}>{PLANET_SYMBOLS[p.name]}</span>
                </td>
                <td style={{ ...S.td, color: isSelected ? "#e0e8ff" : "#c0c0d0" }}>
                  {p.name}
                  {p.retro && <span style={S.retro}>R</span>}
                </td>
                <td style={{ ...S.td, color: ELEMENT_COLORS[SIGNS[p.sign].el] }}>
                  {SIGNS[p.sign].sym}
                </td>
                <td style={{ ...S.td, color: "#a0a8c0" }}>
                  {fmtPos(p.deg, p.min, Math.floor(p.sec))}
                </td>
                <td style={{ ...S.td, color: "#6068a0", fontSize: "11px" }}>
                  {SIGNS[p.sign].name}
                </td>
                <td style={{ ...S.td, color: "#5a6080" }}>
                  {p.house} <span style={{ fontSize: "9px", color: "#404060" }}>({p.housePart}/3)</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={S.sectionTitle}>Дома</div>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}>№</th>
            <th style={S.th}></th>
            <th style={S.th}>Куспид</th>
            <th style={S.th}>Упр.</th>
          </tr>
        </thead>
        <tbody>
          {houses.map((h) => (
            <tr key={h.num}>
              <td style={{ ...S.td, color: "#5060a0" }}>{h.num}</td>
              <td style={{ ...S.td, color: ELEMENT_COLORS[SIGNS[h.sign].el] }}>
                {SIGNS[h.sign].sym}
              </td>
              <td style={{ ...S.td, color: "#808898", fontSize: "11px" }}>
                {Math.floor(h.cusp % 30)}°{String(Math.floor(((h.cusp % 30) % 1) * 60)).padStart(2, "0")}' {SIGNS[h.sign].name}
              </td>
              <td style={{ ...S.td, color: "#6a7090", fontSize: "11px" }}>{h.ruler}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CascadePanel({ planet, levels }) {
  if (!planet) return null;

  const p = VLAD_NATAL.planets.find((pl) => pl.name === planet);
  if (!p) return null;

  const cascade = microCascade(p.min, p.sec, levels);
  const color = PLANET_COLORS[planet] || "#d0d0d8";

  return (
    <div style={S.cascadePanel}>
      <div style={{
        ...S.sectionTitle,
        background: "#0d1030",
        color,
        borderTop: `2px solid ${color}40`,
      }}>
        {PLANET_SYMBOLS[planet]} {planet} — Фрактальный расклад ({levels} уровней)
      </div>

      <div style={{
        padding: "6px 12px",
        fontSize: "11px",
        color: "#7080a0",
        borderBottom: "1px solid #1a1d2a",
      }}>
        Ядро: {SIGNS[p.sign].sym} {fmtPos(p.deg, p.min, Math.floor(p.sec))} {SIGNS[p.sign].name}
        {" "}| Дом {p.house} ({p.housePart}/3) | Сабиан {p.deg + 1}°
      </div>

      {cascade.map((level) => (
        <div key={level.level} style={S.cascadeLevel}>
          <span style={S.levelNum}>Ур.{level.level}</span>
          <span style={{
            ...S.levelSign,
            color: ELEMENT_COLORS[level.sign.el],
          }}>
            {level.sign.sym}
          </span>
          <span style={{
            ...S.levelName,
            color: ELEMENT_COLORS[level.sign.el],
          }}>
            {level.sign.name}
          </span>
          <span style={S.levelDeg}>
            {level.degInt}°{String(level.degMin).padStart(2, "0")}'
          </span>
          <span style={S.levelSab}>саб.{level.sabian}°</span>
          <span style={S.levelSize}>[{fmtSize(level.segmentSize)}]</span>
        </div>
      ))}

      <div style={{
        padding: "6px 12px",
        fontSize: "10px",
        color: "#4a5080",
        borderTop: "1px solid #1a1d2a",
      }}>
        Цепочка: {cascade.map((l) => l.sign.sym).join(" → ")}
        {" "}| Стихии: {
          Object.entries(
            cascade.reduce((acc, l) => {
              const el = l.sign.el === "fire" ? "Огонь" : l.sign.el === "earth" ? "Земля" : l.sign.el === "air" ? "Воздух" : "Вода";
              acc[el] = (acc[el] || 0) + 1;
              return acc;
            }, {})
          ).sort((a, b) => b[1] - a[1]).map(([e, c]) => `${e}(${c})`).join(", ")
        }
      </div>
    </div>
  );
}

// ============================================================
// CIRCULAR CHART
// ============================================================

const SIGN_COLORS_FILL = {
  fire: "#3a1810", earth: "#1a2a10", air: "#0e1a2e", water: "#1a1430",
};
const SIGN_COLORS_STROKE = {
  fire: "#6a3020", earth: "#2a4a1a", air: "#1a3050", water: "#2a2050",
};

function degToXY(deg, asc, r, cx = 250, cy = 250) {
  const angle = (180 + asc - deg) * Math.PI / 180;
  return {
    x: cx + r * Math.cos(angle),
    y: cy - r * Math.sin(angle),
  };
}

function CircularChart({ planets, angles, houses, layers, selectedPlanet, onSelectPlanet }) {
  const asc = angles.ASC.abs;
  const cx = 250;
  const cy = 250;
  const R_OUTER = 220;
  const R_INNER = 195;
  const R_SIGN = 208;
  const R_PLANET = 170;
  const R_DEGREE = 150;
  const R_HOUSE_NUM = 135;

  const signArcs = [];
  for (let i = 0; i < 12; i++) {
    const startDeg = i * 30;
    const endDeg = (i + 1) * 30;
    const el = SIGNS[i].el;

    const p1o = degToXY(startDeg, asc, R_OUTER, cx, cy);
    const p2o = degToXY(endDeg, asc, R_OUTER, cx, cy);
    const p1i = degToXY(startDeg, asc, R_INNER, cx, cy);
    const p2i = degToXY(endDeg, asc, R_INNER, cx, cy);

    const midDeg = startDeg + 15;
    const pMid = degToXY(midDeg, asc, R_SIGN, cx, cy);

    signArcs.push({ i, el, startDeg, endDeg, p1o, p2o, p1i, p2i, pMid, sym: SIGNS[i].sym });
  }

  const houseLines = houses.map((h) => {
    const pOuter = degToXY(h.cusp, asc, R_INNER, cx, cy);
    const pInner = degToXY(h.cusp, asc, 40, cx, cy);
    const midCusp = h.num < 12
      ? (h.cusp + houses[h.num].cusp) / 2
      : (h.cusp + houses[0].cusp + 360) / 2;
    const pNum = degToXY(midCusp % 360, asc, R_HOUSE_NUM, cx, cy);
    return { ...h, pOuter, pInner, pNum };
  });

  const planetDots = planets.map((p) => {
    const pos = degToXY(p.abs, asc, R_PLANET, cx, cy);
    const color = PLANET_COLORS[p.name] || "#aaa";
    const isSelected = selectedPlanet === p.name;
    return { ...p, pos, color, isSelected };
  });

  const angleMarkers = [
    { name: "ASC", abs: angles.ASC.abs, color: "#e05040" },
    { name: "MC", abs: angles.MC.abs, color: "#40a0e0" },
    { name: "DSC", abs: angles.DSC.abs, color: "#e05040" },
    { name: "IC", abs: angles.IC.abs, color: "#40a0e0" },
  ];

  return (
    <svg viewBox="0 0 500 500" style={{ width: "100%", maxWidth: "700px" }}>
      <circle cx={cx} cy={cy} r={R_OUTER} fill="none" stroke="#1a1d30" strokeWidth="0.5" />
      <circle cx={cx} cy={cy} r={R_INNER} fill="none" stroke="#2a2d42" strokeWidth="0.5" />
      <circle cx={cx} cy={cy} r="60" fill="none" stroke="#1a1d30" strokeWidth="0.5" />

      {signArcs.map(({ i, el, startDeg, endDeg, p1o, p2o, p1i, p2i, pMid, sym }) => {
        const a1 = (180 + asc - startDeg) * Math.PI / 180;
        const a2 = (180 + asc - endDeg) * Math.PI / 180;
        const x1o = cx + R_OUTER * Math.cos(a1);
        const y1o = cy - R_OUTER * Math.sin(a1);
        const x2o = cx + R_OUTER * Math.cos(a2);
        const y2o = cy - R_OUTER * Math.sin(a2);
        const x1i = cx + R_INNER * Math.cos(a1);
        const y1i = cy - R_INNER * Math.sin(a1);
        const x2i = cx + R_INNER * Math.cos(a2);
        const y2i = cy - R_INNER * Math.sin(a2);

        const path = `M${x1o},${y1o} A${R_OUTER},${R_OUTER} 0 0,0 ${x2o},${y2o} L${x2i},${y2i} A${R_INNER},${R_INNER} 0 0,1 ${x1i},${y1i} Z`;

        return (
          <g key={i}>
            <path d={path} fill={SIGN_COLORS_FILL[el]} stroke={SIGN_COLORS_STROKE[el]} strokeWidth="0.5" />
            <text x={pMid.x} y={pMid.y} textAnchor="middle" dominantBaseline="central"
              style={{ fontSize: "14px", fill: ELEMENT_COLORS[el], opacity: 0.8 }}>
              {sym}
            </text>
          </g>
        );
      })}

      {houseLines.map((h) => (
        <g key={h.num}>
          <line x1={h.pOuter.x} y1={h.pOuter.y} x2={h.pInner.x} y2={h.pInner.y}
            stroke={h.num === 1 || h.num === 10 ? "#4a5080" : "#1e2038"}
            strokeWidth={h.num === 1 || h.num === 4 || h.num === 7 || h.num === 10 ? "1" : "0.3"} />
          <text x={h.pNum.x} y={h.pNum.y} textAnchor="middle" dominantBaseline="central"
            style={{ fontSize: "9px", fill: "#3a3d60" }}>
            {h.num}
          </text>
        </g>
      ))}

      {angleMarkers.map(({ name, abs, color }) => {
        const pOuter = degToXY(abs, asc, R_OUTER + 4, cx, cy);
        const pInner = degToXY(abs, asc, 36, cx, cy);
        const pLabel = degToXY(abs, asc, R_OUTER + 18, cx, cy);
        return (
          <g key={name}>
            <line x1={pOuter.x} y1={pOuter.y} x2={pInner.x} y2={pInner.y}
              stroke={color} strokeWidth="1.5" opacity="0.6" />
            <text x={pLabel.x} y={pLabel.y} textAnchor="middle" dominantBaseline="central"
              style={{ fontSize: "10px", fill: color, fontWeight: "500" }}>
              {name}
            </text>
          </g>
        );
      })}

      {layers.natal && planetDots.map((p) => (
        <g key={p.name} onClick={() => onSelectPlanet(p.name)} style={{ cursor: "pointer" }}>
          <circle cx={p.pos.x} cy={p.pos.y} r={p.isSelected ? 14 : 11}
            fill={p.isSelected ? p.color + "30" : "#0d0f1a"}
            stroke={p.color} strokeWidth={p.isSelected ? "1.5" : "0.8"} />
          <text x={p.pos.x} y={p.pos.y} textAnchor="middle" dominantBaseline="central"
            style={{
              fontSize: p.isSelected ? "12px" : "10px",
              fill: p.color,
              fontWeight: p.isSelected ? "600" : "400",
            }}>
            {PLANET_SYMBOLS[p.name] || p.name[0]}
          </text>
          {p.retro && (
            <text x={p.pos.x + 12} y={p.pos.y - 8} style={{ fontSize: "7px", fill: "#e05040" }}>R</text>
          )}
        </g>
      ))}

      <text x={cx} y={cy - 8} textAnchor="middle" style={{ fontSize: "10px", fill: "#3a3d60" }}>
        {layers.natal ? "● Натал" : ""}
      </text>
      <text x={cx} y={cy + 6} textAnchor="middle" style={{ fontSize: "10px", fill: "#e85d3a", opacity: layers.transit ? 1 : 0.2 }}>
        {layers.transit ? "● Транзит" : ""}
      </text>
      <text x={cx} y={cy + 20} textAnchor="middle" style={{ fontSize: "10px", fill: "#8b7ec8", opacity: layers.horary ? 1 : 0.2 }}>
        {layers.horary ? "● Хорар" : ""}
      </text>
    </svg>
  );
}

// ============================================================
// MAIN APP
// ============================================================

export default function QuantarionPanel() {
  const [selectedPlanet, setSelectedPlanet] = useState("Уран");
  const [cascadeLevels, setCascadeLevels] = useState(6);
  const [layers, setLayers] = useState({ natal: true, transit: false, horary: false, matrix: false });
  const [timerOn, setTimerOn] = useState(false);
  const [now, setNow] = useState(new Date());
  const [theme, setTheme] = useState("dark-high-contrast");
  const [data, setData] = useState({
    name: VLAD_NATAL.name,
    date: VLAD_NATAL.date,
    time: VLAD_NATAL.time,
    tz: "+6",
    lat: String(VLAD_NATAL.lat),
    lon: String(VLAD_NATAL.lon),
    place: VLAD_NATAL.place,
    ascDeg: "12",
    ascMin: "27",
    ascSign: "5",
    task: "natal",
  });

  useEffect(() => {
    if (!timerOn) return;
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, [timerOn]);

  const clockStr = now.toLocaleTimeString("ru-RU", { hour12: false });
  const dateStr = now.toLocaleDateString("ru-RU");

  return (
    <div style={S.app}>
      <InputPanel
        data={data}
        setData={setData}
        layers={layers}
        setLayers={setLayers}
        timerOn={timerOn}
        setTimerOn={setTimerOn}
        clockStr={clockStr}
        dateStr={dateStr}
        theme={theme}
        setTheme={setTheme}
      />

      <div style={S.body}>
        <div style={S.chartArea}>
          <CircularChart
            planets={VLAD_NATAL.planets}
            angles={VLAD_NATAL.angles}
            houses={VLAD_NATAL.houses}
            layers={layers}
            selectedPlanet={selectedPlanet}
            onSelectPlanet={setSelectedPlanet}
          />
        </div>

        <div style={S.tableArea}>
          <div style={{
            padding: "4px 12px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            borderBottom: "1px solid #2a2d42",
            background: "#141628",
          }}>
            <span style={{ fontSize: "10px", color: "#5060a0" }}>Карта:</span>
            <span style={{ fontSize: "11px", color: "#a0a8c8" }}>
              {data.name} | {data.date} {data.time} {data.tz}
            </span>
            <span style={{ fontSize: "10px", color: VLAD_NATAL.isDay ? "#f0c040" : "#6070a0" }}>
              {VLAD_NATAL.isDay ? "☉ дневная" : "☽ ночная"}
            </span>
          </div>

          <PlanetTable
            planets={VLAD_NATAL.planets}
            angles={VLAD_NATAL.angles}
            houses={VLAD_NATAL.houses}
            selected={selectedPlanet}
            onSelect={setSelectedPlanet}
          />

          <div style={{
            padding: "4px 12px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            background: "#141628",
            borderTop: "1px solid #2a2d42",
          }}>
            <span style={{ fontSize: "10px", color: "#5060a0" }}>Глубина:</span>
            {[3, 4, 5, 6].map((n) => (
              <button
                key={n}
                style={{
                  ...S.btn,
                  padding: "2px 8px",
                  fontSize: "10px",
                  ...(cascadeLevels === n ? S.btnActive : {}),
                }}
                onClick={() => setCascadeLevels(n)}
              >
                {n}
              </button>
            ))}
          </div>

          <CascadePanel planet={selectedPlanet} levels={cascadeLevels} />
        </div>
      </div>
    </div>
  );
}
