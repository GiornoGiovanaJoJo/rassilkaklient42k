/*
 * Русификация редактора писем (EmailBuilder.js).
 *
 * Редактор — готовая минифицированная сборка стороннего конструктора, и его
 * подписи зашиты в бандле на английском. Пересобрать из исходников нечем,
 * поэтому подписи переводятся на лету: словарь «английское → русское» плюс
 * наблюдатель за DOM, который переводит заново после каждой перерисовки React.
 *
 * Главное — НЕ ТРОГАТЬ текст самого письма, который набирает пользователь.
 * Разделение надёжное: подписи интерфейса (панель блоков, инспектор свойств,
 * кнопки) обычным текстом и НЕ редактируемы, а текст письма в холсте лежит
 * внутри contenteditable / textarea / pre / code. Поэтому перевод пропускает
 * всё, что находится внутри редактируемой области, и работает только с хромом.
 *
 * Перевод идемпотентен: русскую строку в словаре не найти, второй проход её не
 * меняет — зацикливания с наблюдателем не возникает.
 */
(function () {
  "use strict";

  var DICT = {
    // --- Панели, вкладки, кнопки ---
    "Inspect": "Свойства",
    "Styles": "Оформление",
    "Preview": "Предпросмотр",
    "Edit": "Редактировать",
    "Editor": "Редактор",
    "Add": "Добавить",
    "Import JSON": "Импорт JSON",
    "Share": "Поделиться",
    "Download": "Скачать",
    "Save": "Сохранить",

    // --- Названия блоков (в меню добавления и в заголовке инспектора) ---
    "Heading": "Заголовок",
    "Text": "Текст",
    "Button": "Кнопка",
    "Image": "Картинка",
    "Avatar": "Аватар",
    "Divider": "Разделитель",
    "Spacer": "Отступ",
    "Columns": "Колонки",
    "Container": "Контейнер",
    "Html": "HTML‑код",
    "Heading block": "Блок «Заголовок»",
    "Text block": "Блок «Текст»",
    "Button block": "Блок «Кнопка»",
    "Image block": "Блок «Картинка»",
    "Avatar block": "Блок «Аватар»",
    "Divider block": "Блок «Разделитель»",
    "Spacer block": "Блок «Отступ»",
    "Columns block": "Блок «Колонки»",
    "Container block": "Блок «Контейнер»",
    "Html block": "Блок «HTML‑код»",

    // --- Свойства блоков ---
    "Width": "Ширина",
    "Height": "Высота",
    "Color": "Цвет",
    "Text color": "Цвет текста",
    "Background color": "Цвет фона",
    "Font family": "Шрифт",
    "Font weight": "Насыщенность",
    "Font size": "Размер шрифта",
    "Alignment": "Выравнивание",
    "Content alignment": "Выравнивание содержимого",
    "Padding": "Отступы",
    "Border radius": "Скругление углов",
    "Border color": "Цвет рамки",
    "Number of columns": "Число колонок",
    "Columns gap": "Промежуток между колонками",
    "Source URL": "Адрес картинки",
    "Alt text": "Подпись, если картинка не открылась",
    "Click through URL": "Ссылка (куда ведёт кнопка)",
    "Content": "Содержимое",
    "Shape": "Форма",
    "Size": "Размер",
    "Level": "Уровень",
    "Markdown": "Markdown",

    // --- Значения: шрифты ---
    "Modern sans": "Без засечек (современный)",
    "Book sans": "Без засечек (книжный)",
    "Organic sans": "Без засечек (мягкий)",
    "Geometric sans": "Без засечек (геометрический)",
    "Heavy sans": "Без засечек (жирный)",
    "Rounded sans": "Без засечек (скруглённый)",
    "Modern serif": "С засечками (современный)",
    "Book serif": "С засечками (книжный)",
    "Monospace": "Моноширинный",

    // --- Значения: форма кнопки / аватара ---
    "Rectangle": "Прямоугольник",
    "Rounded": "Скруглённый",
    "Pill": "Капсула",
    "Circle": "Круг",
    "Square": "Квадрат",

    // --- Значения: насыщенность и выравнивание ---
    "Regular": "Обычный",
    "Bold": "Жирный",
    "Left": "Слева",
    "Center": "По центру",
    "Right": "Справа",
    "Top": "Сверху",
    "Bottom": "Снизу",

    // --- Разделы инспектора и холст ---
    "Global": "Общее",
    "Dimensions": "Размеры",
    "Click on a block to inspect.": "Нажмите на блок, чтобы увидеть его настройки.",
    "Backdrop color": "Цвет подложки",
    "Canvas color": "Цвет холста",
    "Canvas border color": "Цвет рамки холста",
    "Canvas border radius": "Скругление углов холста",
    "Button color": "Цвет кнопки",
    "Image URL": "Адрес картинки",
    "Upload image": "Загрузить картинку",
    "Plain text": "Простой текст",
    "Nested Text": "Вложенный текст",
    "Markdown (GitHub flavored)": "Markdown (GitHub)",

    // --- Подсказки на кнопках верхней панели ---
    "Desktop view": "Вид на компьютере",
    "Mobile view": "Вид на телефоне",
    "Download JSON file": "Скачать файл JSON",
    "Share current template": "Поделиться шаблоном",
    "HTML output": "HTML‑код письма",
    "JSON output": "JSON письма",
    "Open dashboard": "Открыть панель",
    "Expand": "Развернуть",
    "Move up": "Выше",
    "Move down": "Ниже",
    "Strikethrough (select text first)": "Зачёркнутый (сначала выделите текст)",
    "Text color (select text first)": "Цвет текста (сначала выделите текст)",

    // --- Готовые шаблоны в списке слева ---
    "Empty": "Пустой",
    "Welcome email": "Приветственное письмо",
    "One-time passcode (OTP)": "Одноразовый код (OTP)",
    "Reset password": "Сброс пароля",
    "E-commerce receipt": "Чек интернет‑магазина",
    "Subscription receipt": "Чек подписки",
    "Reservation reminder": "Напоминание о брони",
    "Post metrics": "Статистика публикации",
    "Respond to inquiry": "Ответ на обращение",

    // --- Диалоги ---
    "This will override your current template.": "Это заменит текущий шаблон."
  };

  // Атрибуты-подписи, которые тоже переводим (подсказки, placeholder).
  var ATTRS = ["placeholder", "title", "aria-label"];

  // Тег/состояние, внутри которого лежит ПОЛЬЗОВАТЕЛЬСКИЙ контент — не трогаем.
  var SKIP_TAGS = { TEXTAREA: 1, PRE: 1, CODE: 1, SCRIPT: 1, STYLE: 1, INPUT: 1 };

  function isInUserContent(el) {
    for (var node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (SKIP_TAGS[node.tagName]) return true;
      if (node.isContentEditable) return true;
    }
    return false;
  }

  function translated(value) {
    if (value == null) return null;
    var trimmed = value.trim();
    if (!trimmed) return null;
    var ru = DICT[trimmed];
    if (ru === undefined || ru === trimmed) return null;
    // Сохраняем окружающие пробелы исходной строки.
    return value.replace(trimmed, ru);
  }

  function translateTextNode(node) {
    var parent = node.parentElement;
    if (!parent || isInUserContent(parent)) return;
    var next = translated(node.nodeValue);
    if (next !== null) node.nodeValue = next;
  }

  function translateAttrs(el) {
    if (!el.getAttribute) return;
    for (var i = 0; i < ATTRS.length; i++) {
      var name = ATTRS[i];
      if (!el.hasAttribute(name)) continue;
      var next = translated(el.getAttribute(name));
      if (next !== null) el.setAttribute(name, next);
    }
  }

  function translateTree(root) {
    if (!root) return;
    // Текстовые узлы.
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var textNodes = [];
    var n;
    while ((n = walker.nextNode())) textNodes.push(n);
    for (var i = 0; i < textNodes.length; i++) translateTextNode(textNodes[i]);
    // Атрибуты-подписи.
    if (root.nodeType === 1) translateAttrs(root);
    if (root.querySelectorAll) {
      var els = root.querySelectorAll("*");
      for (var j = 0; j < els.length; j++) {
        if (!isInUserContent(els[j])) translateAttrs(els[j]);
      }
    }
  }

  var scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(function () {
      scheduled = false;
      translateTree(document.body);
    });
  }

  function start() {
    document.documentElement.setAttribute("lang", "ru");
    translateTree(document.body);
    new MutationObserver(schedule).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true
    });
  }

  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);
})();
