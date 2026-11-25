'use strict';

const icons = {
  brand: '<path d="M3 12h4l2-5 4 10 2-5h6"/><path d="M4 9V5h16v4M4 15v4h16v-4"/>',
  activity: '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
  stethoscope: '<path d="M6 3H4v6a5 5 0 0 0 10 0V3h-2m-3 11v2a4 4 0 0 0 8 0v-2"/><circle cx="17" cy="11" r="3"/>',
  trend: '<path d="M3 19h18M4 15l5-5 4 3 6-7m-5 0h5v5"/>',
  message: '<path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.3-3a7.5 7.5 0 1 1 13.7-4.5Z"/><path d="M9 11h7m-7 3h4"/>',
  history: '<path d="M4.3 8.7A8.5 8.5 0 1 1 4 15M4 4v5h5m3-2v5l3 2"/>',
  layers: '<path d="M12 3 3 8l9 5 9-5-9-5ZM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 1 1 8 0v3m-4 4v3"/>',
  chevron: '<path d="m10 6 6 6-6 6"/>',
  code: '<path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16"/>',
  audio: '<path d="M3 10v4m4-8v12m5-16v20m5-16v12m4-8v4"/>',
  fuel: '<path d="M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h12M5 11h8m1 2h2a2 2 0 0 1 2 2v2a2 2 0 0 0 4 0v-6l-3-3m-1 2 2 2h2"/>',
  gauge: '<path d="M4 18a9 9 0 1 1 16 0H4Zm8-3 4-5M6 12h1m5-5v1m5 4h1"/><circle cx="12" cy="15" r="1"/>',
  car: '<path d="m5 11 2-5h10l2 5M6 17v2m12-2v2M4 17h16v-4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v4Zm3-3h2m6 0h2"/>',
  spark: '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Zm6 13 1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2Z"/>',
  scan: '<path d="M8 4H4v4m12-4h4v4M4 16v4h4m12-4v4h-4M4 12h16"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  upload: '<path d="M12 16V4m-4 4 4-4 4 4M4 16v4h16v-4"/>',
  download: '<path d="M12 4v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
  report: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8m-8 4h8m-8 4h5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/>'
};

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function setIcon(node, name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '24');
  svg.setAttribute('height', '24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.7');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = icons[name];
  node.append(svg);
}

function icon(name, className) {
  const node = element('span', className);
  node.dataset.icon = name;
  setIcon(node, name);
  return node;
}

document.querySelectorAll('[data-icon]').forEach(node => setIcon(node, node.dataset.icon));

const pages = {
  diagnosis: 'Диагностика', prediction: 'Прогноз', assistant: 'AI-ассистент',
  history: 'История', model: 'О модели'
};
const kinds = {
  diagnosis: 'Диагностика по симптомам', dtc: 'Код OBD-II', audio: 'Анализ звука',
  fuel: 'Расход топлива', telemetry: 'Телеметрия', prediction: 'Прогноз', assistant: 'Справочник'
};
const modes = {
  symptoms: 'Опишите симптомы и нажмите «Начать диагностику».',
  dtc: 'Введите код, чтобы получить его описание.',
  audio: 'Загрузите WAV-файл, чтобы увидеть параметры сигнала.',
  fuel: 'Введите расход, чтобы сравнить показания.',
  telemetry: 'Загрузите CSV, чтобы увидеть параметры поездки.'
};
const tabs = [...document.querySelectorAll('[data-mode]')];
const modeResults = new Map();
let activeMode = 'symptoms';

function showEmpty(container, title, caption, iconName) {
  const view = element('div', 'empty');
  view.append(icon(iconName, 'empty-icon'), element('h3', '', title), element('p', '', caption));
  container.replaceChildren(view);
}

function sourceLink(label, url) {
  try {
    const target = new URL(url);
    if (target.protocol !== 'https:') return null;
    const link = element('a', 'source-link', label);
    link.href = target.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  } catch {
    return null;
  }
}

const numberFormat = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 2});
const metricFormat = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 3});
const percentFormat = new Intl.NumberFormat('ru-RU', {style: 'percent', maximumFractionDigits: 2});
const dateFormat = new Intl.DateTimeFormat('ru-RU', {dateStyle: 'medium', timeStyle: 'short'});
const number = (value, unit = '') => typeof value === 'number' ? numberFormat.format(value) + unit : '—';
const percent = value => typeof value === 'number' ? percentFormat.format(value) : '—';

function list(values) {
  const items = element('ul', '');
  values.forEach(value => items.append(element('li', '', value)));
  return items;
}

function metrics(values) {
  const root = element('dl', 'metrics');
  values.forEach(([label, value]) => {
    const entry = element('div', '');
    entry.append(element('dt', '', label), element('dd', '', value));
    root.append(entry);
  });
  return root;
}

function recommendation(body, content) {
  if (!content) return;
  const root = element('div', 'recommendation');
  root.append(element('h4', '', 'Что проверить'), element('p', '', content));
  body.append(root);
}

function plot(values, label, waveform = false) {
  const data = values.filter(Number.isFinite);
  if (data.length < 2) return element('p', 'plot-label', 'Для графика нужны два измерения.');
  const figure = element('div', '');
  const canvas = element('canvas', 'plot');
  canvas.width = 640;
  canvas.height = 164;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', label);
  figure.append(canvas, element('p', 'plot-label', label));
  const ctx = canvas.getContext('2d');
  if (!ctx) return figure;
  const width = canvas.width;
  const height = canvas.height;
  const pad = 14;
  ctx.strokeStyle = '#cfe3da';
  for (const fraction of [.25, .5, .75]) {
    ctx.beginPath();
    ctx.moveTo(pad, height * fraction);
    ctx.lineTo(width - pad, height * fraction);
    ctx.stroke();
  }
  ctx.strokeStyle = '#158262';
  ctx.lineWidth = 3;
  ctx.beginPath();
  let low = data[0];
  let high = data[0];
  for (const value of data) {
    low = Math.min(low, value);
    high = Math.max(high, value);
  }
  if (low === high) high = low + 1;
  data.forEach((value, index) => {
    const x = pad + index * (width - 2 * pad) / (data.length - 1);
    if (waveform) {
      const offset = Math.min(Math.abs(value), 1) * (height / 2 - pad);
      ctx.moveTo(x, height / 2 - offset);
      ctx.lineTo(x, height / 2 + offset);
    } else {
      const y = height - pad - (value - low) / (high - low) * (height - 2 * pad);
      if (index) ctx.lineTo(x, y);
      else ctx.moveTo(x, y);
    }
  });
  ctx.stroke();
  return figure;
}

function renderSources(body, sources) {
  if (!sources?.length) return;
  const links = element('ul', '');
  for (const source of sources) {
    const link = sourceLink(source.label || 'Открыть источник', source.url);
    if (link) {
      const item = element('li', '');
      item.append(link);
      links.append(item);
    }
  }
  if (links.childElementCount) body.append(links);
}

function addDtc(body, result) {
  const title = [result.code, result.title].filter(Boolean).join(' · ');
  body.append(element('h3', '', title || 'Код OBD-II'));
  if (result.summary) body.append(element('p', '', result.summary));
  if (result.checkpoints?.length) body.append(list(result.checkpoints));
  recommendation(body, result.recommendation);
  renderSources(body, result.sources);
}

function vehicleTitle(record) {
  const {make, model, year, engine} = record?.vehicle || {};
  return [[make, model].filter(Boolean).join(' '), year ? year + ' г.' : '', engine].filter(Boolean).join(' · ');
}

function renderResult(container, kind, result, record) {
  const body = element('div', 'output');
  const vehicle = vehicleTitle(record);
  if (vehicle) body.append(element('p', 'result-vehicle', vehicle));

  if (kind === 'diagnosis') {
    const heading = result.candidates?.length ? 'Категории по описанию симптомов' :
      result.status === 'unavailable' ? 'Модель недоступна' : 'Нужно больше подробностей';
    body.append(element('h3', '', heading));
    for (const candidate of result.candidates || []) {
      const section = element('section', 'candidate');
      const heading = element('header', 'candidate-header');
      const score = element('span', '', percent(candidate.score));
      score.title = 'Балл модели для категории жалобы';
      heading.append(element('strong', '', candidate.label), score);
      const track = element('div', 'probability-track');
      track.setAttribute('aria-hidden', 'true');
      const fill = element('span', '');
      fill.style.width = Math.max(0, Math.min(candidate.score * 100, 100)) + '%';
      track.append(fill);
      section.append(heading, track);
      if (candidate.description) section.append(element('p', '', candidate.description));
      if (candidate.checks?.length) section.append(list(candidate.checks));
      body.append(section);
    }
    if (result.note) body.append(element('p', '', result.note));
    if (result.vehicle_note) body.append(element('p', '', result.vehicle_note));
    if (result.dtc) addDtc(body, result.dtc);
  } else if (kind === 'dtc') {
    addDtc(body, result);
  } else {
    body.append(element('h3', '', result.title || kinds[kind]));
    if (result.summary) body.append(element('p', '', result.summary));
    if (kind === 'audio') {
      body.append(metrics([
        ['Длительность', number(result.duration_seconds, ' с')],
        ['Частота выборки', number(result.sample_rate_hz, ' Гц')],
        ['Каналы', number(result.channels)], ['Пик спектра', number(result.dominant_frequency_hz, ' Гц')],
        ['Среднекв. уровень', number(result.rms_dbfs, ' dBFS')], ['Пиковый уровень', number(result.peak_dbfs, ' dBFS')]
      ]));
      if (result.waveform?.length) body.append(plot(result.waveform, 'Пиковая амплитуда сигнала по времени', true));
    } else if (kind === 'fuel') {
      body.append(metrics([
        ['Текущий', number(result.actual, ' л/100 км')],
        [result.baseline_source === 'history' ? 'Из истории' : 'Обычный', number(result.baseline, ' л/100 км')],
        ['Изменение', number(result.delta_pct, ' %')]
      ]));
      if (result.history?.length > 1) body.append(plot(result.history, 'Расход по сохранённым замерам, л/100 км'));
    } else if (kind === 'telemetry') {
      const latest = result.latest || {};
      body.append(metrics([
        ['Замеры', number(result.sample_count)], ['Температура', number(latest.coolant_c, ' °C')],
        ['Обороты', number(latest.rpm, ' об/мин')], ['Скорость', number(latest.speed_kmh, ' км/ч')]
      ]));
      if (result.samples?.length) body.append(plot(result.samples.map(sample => sample.coolant_c), 'Температура охлаждающей жидкости за поездку, °C'));
      const link = element('a', 'source-link', 'Оценить тренд');
      link.href = '#prediction';
      body.append(link);
    } else if (kind === 'prediction') {
      body.append(metrics([
        ['Последний замер', number(result.current_c, ' °C')],
        ['Через ' + number(result.horizon_seconds, ' с'), number(result.projected_c, ' °C')],
        ['Тренд', number(result.slope_c_per_min, ' °C/мин')],
        ['R²', number(result.r_squared)]
      ]));
    }
    if (result.checkpoints?.length) body.append(list(result.checkpoints));
    recommendation(body, result.recommendation);
    renderSources(body, result.sources);
  }
  container.replaceChildren(body);
}

function selectMode(mode) {
  activeMode = mode;
  for (const tab of tabs) {
    const selected = tab.dataset.mode === mode;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
  }
  const container = document.getElementById('result-diagnosis');
  const saved = modeResults.get(mode);
  if (saved) renderResult(container, saved.kind, saved.result, saved.record);
  else showEmpty(container, 'Здесь появится результат', modes[mode], 'activity');
}

for (const [index, tab] of tabs.entries()) {
  tab.addEventListener('click', () => selectMode(tab.dataset.mode));
  tab.addEventListener('keydown', event => {
    const adjacent = {ArrowLeft: (index + tabs.length - 1) % tabs.length, ArrowRight: (index + 1) % tabs.length, Home: 0, End: tabs.length - 1};
    const next = adjacent[event.key];
    if (typeof next !== 'number') return;
    event.preventDefault();
    tabs[next].focus();
    selectMode(tabs[next].dataset.mode);
  });
}

function readError(data) {
  return typeof data.error === 'string' ? data.error : 'Сервер не смог обработать запрос. Попробуйте ещё раз.';
}

async function api(endpoint, options) {
  let response;
  try {
    response = await fetch('/api/' + endpoint, options);
  } catch {
    throw new Error('Не удалось подключиться к локальному серверу.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(readError(data));
  return data;
}

document.querySelectorAll('.check-form').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const endpoint = form.dataset.endpoint;
    const destination = form.dataset.result;
    const mode = activeMode;
    const submit = form.querySelector('button[type=submit]');
    const error = form.querySelector('.error');
    const original = [...submit.childNodes];
    const formData = new FormData(form);
    const options = {method: 'POST', body: formData};
    if (form.enctype !== 'multipart/form-data') {
      options.headers = {'Content-Type': 'application/json'};
      options.body = JSON.stringify(Object.fromEntries(formData));
    }
    submit.disabled = true;
    submit.replaceChildren(document.createTextNode('Обрабатываем…'));
    error.hidden = true;
    try {
      const data = await api(endpoint, options);
      const kind = data.record?.kind || (endpoint === 'diagnose' ? 'diagnosis' : endpoint);
      if (destination === 'diagnosis') modeResults.set(mode, {kind, ...data});
      if (destination !== 'diagnosis' || mode === activeMode) {
        renderResult(document.getElementById('result-' + destination), kind, data.result, data.record);
      }
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      submit.disabled = false;
      submit.replaceChildren(...original);
    }
  });
});

const examples = {
  symptoms: {
    make: 'Haval', model: 'M6', year: '2024', engine: '1.5 Turbo',
    symptoms: 'При запуске двигателя слышен странный стук.',
    additional: 'Увеличился расход топлива.', dtc: ''
  },
  dtc: {code: 'P0301'},
  fuel: {actual: '10.8', baseline: '8.7'}
};

document.querySelectorAll('[data-example]').forEach(button => {
  button.addEventListener('click', () => {
    const form = button.closest('[role=tabpanel]').querySelector('form');
    for (const [name, value] of Object.entries(examples[button.dataset.example])) {
      form.elements.namedItem(name).value = value;
    }
  });
});

document.querySelectorAll('[data-question]').forEach(button => {
  button.addEventListener('click', () => {
    const field = button.closest('form').elements.namedItem('issue');
    field.value = button.dataset.question;
    field.focus();
  });
});

document.querySelectorAll('input[type=file]').forEach(field => {
  field.addEventListener('change', () => {
    field.closest('label').querySelector('.file-name').textContent = field.files[0]?.name || '';
  });
});

async function showHistory() {
  const root = document.getElementById('history-list');
  const result = document.getElementById('result-history');
  showEmpty(root, 'Загрузка истории…', 'Читаем сохранённые проверки.', 'history');
  showEmpty(result, 'Проверка не выбрана', 'Выберите запись в списке.', 'report');
  try {
    const {items} = await api('history');
    if (!items.length) {
      showEmpty(root, 'История пуста', 'После первой проверки результат появится здесь.', 'history');
      return;
    }
    const entries = element('div', 'history-list');
    for (const record of items) {
      const button = element('button', 'history-item');
      button.type = 'button';
      button.setAttribute('aria-pressed', 'false');
      const date = new Date(record.created_at);
      const metadata = [Number.isFinite(date.getTime()) ? dateFormat.format(date) : '', vehicleTitle(record), record.input?.filename].filter(Boolean).join(' · ');
      button.append(element('strong', '', kinds[record.kind] || 'Проверка'), element('span', '', metadata));
      button.addEventListener('click', () => {
        for (const previous of entries.querySelectorAll('.is-current')) {
          previous.classList.remove('is-current');
          previous.setAttribute('aria-pressed', 'false');
        }
        button.classList.add('is-current');
        button.setAttribute('aria-pressed', 'true');
        renderResult(result, record.kind, record.result, record);
      });
      entries.append(button);
    }
    root.replaceChildren(entries);
  } catch (failure) {
    showEmpty(root, 'История недоступна', failure.message, 'info');
  }
}

async function showModel() {
  const root = document.getElementById('model-content');
  showEmpty(root, 'Загрузка метрик…', 'Читаем отчёт обучения.', 'layers');
  try {
    const {result} = await api('model');
    const body = element('div', 'output');
    body.append(element('h3', '', result.name || 'Классификация по описанию'));
    if (result.status === 'unavailable') {
      body.append(element('p', '', 'Файл с метриками пока недоступен.'));
    } else {
      body.append(metrics([
        ['Точность', percent(result.accuracy)], ['Macro-F1', metricFormat.format(result.macro_f1)],
        ['Тестовые обращения', number(result.test_size)], ['Обучающие обращения', number(result.train_size)]
      ]));
      body.append(element('p', '', 'Модель классифицирует описания по категориям компонентов из обращений NHTSA. Тестовая выборка содержит отдельные сочетания марки и модели.'));
      body.append(element('p', '', 'Метрики измерены на англоязычных обращениях. Для русского ввода используется словарь автомобильных фраз, качество русского ввода отдельно не измерялось.'));
      if (result.classes?.length) {
        body.append(element('h4', '', 'Категории компонентов'));
        body.append(list(result.classes.map(item => typeof item === 'string' ? item : item.label || item.id)));
      }
    }
    const source = sourceLink(result.source_name || 'Источник данных NHTSA', result.source_url);
    if (source) body.append(source);
    root.replaceChildren(body);
  } catch (failure) {
    showEmpty(root, 'Метрики недоступны', failure.message, 'info');
  }
}

function openPage() {
  const hash = location.hash.slice(1);
  const active = Object.hasOwn(pages, hash) ? hash : 'diagnosis';
  document.querySelectorAll('.page').forEach(page => { page.hidden = page.id !== 'page-' + active; });
  document.querySelectorAll('.menu-link').forEach(link => {
    const selected = link.dataset.page === active;
    link.classList.toggle('is-active', selected);
    if (selected) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.getElementById('location-name').textContent = pages[active];
  if (active === 'history') void showHistory();
  if (active === 'model') void showModel();
  window.scrollTo(0, 0);
}

selectMode(activeMode);
showEmpty(document.getElementById('result-prediction'), 'Здесь появится прогноз', 'Рассчитайте тренд по журналу поездки.', 'trend');
showEmpty(document.getElementById('result-assistant'), 'Здесь появится ответ', 'Введите код или автомобильный термин.', 'message');
window.addEventListener('hashchange', openPage);
openPage();
