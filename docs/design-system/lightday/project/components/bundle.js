/* @ds-bundle: {"format":4,"namespace":"Lightday","components":[{"name":"AppBar"},{"name":"Button"},{"name":"MicButton"},{"name":"StatusPill"},{"name":"Field"},{"name":"Card"},{"name":"ListRow"},{"name":"SpokenGuide"},{"name":"PaperSheet"},{"name":"AppTile"}]} */
(function () {
  var React = window.React;
  var h = React.createElement;

  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) if (arguments[i]) out.push(arguments[i]);
    return out.join(' ');
  }
  function omit(obj, keys) {
    var o = {};
    for (var k in obj) if (Object.prototype.hasOwnProperty.call(obj, k) && keys.indexOf(k) < 0) o[k] = obj[k];
    return o;
  }

  /* Inline line icons: 24 grid, 2px stroke, round caps, currentColor. */
  function Icon(name, size) {
    var s = size || 20;
    var paths = {
      mic: [h('rect', { key: 'a', x: 9, y: 3, width: 6, height: 11, rx: 3 }), h('path', { key: 'b', d: 'M6 11a6 6 0 0 0 12 0' }), h('path', { key: 'c', d: 'M12 17v4' })],
      stop: [h('rect', { key: 'a', x: 7, y: 7, width: 10, height: 10, rx: 2 })],
      arrow: [h('path', { key: 'a', d: 'M5 12h14' }), h('path', { key: 'b', d: 'M13 6l6 6-6 6' })]
    };
    return h('svg', { width: s, height: s, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': 'true', focusable: 'false' }, paths[name]);
  }

  /* The mark: a half sun resting above a horizon. */
  function Mark(props) {
    var s = props.size || 28;
    return h('svg', { className: 'ld-mark', width: s, height: s, viewBox: '0 0 32 32', 'aria-hidden': 'true', focusable: 'false' },
      h('path', { className: 'ld-mark-sun', d: 'M6 19a10 10 0 0 1 20 0z' }),
      h('rect', { className: 'ld-mark-horizon', x: 3, y: 22, width: 26, height: 3.5, rx: 1.75 })
    );
  }

  function Button(props) {
    var variant = props.variant || 'ghost';
    var size = props.size || 'md';
    var rest = omit(props, ['variant', 'size', 'icon', 'block', 'className', 'children', 'type']);
    return h('button', Object.assign({ type: props.type || 'button' }, rest, {
      className: cx('ld-btn', 'ld-btn-' + variant, size === 'lg' && 'ld-btn-lg', props.block && 'ld-btn-block', props.className)
    }), props.icon ? Icon(props.icon, 18) : null, props.children);
  }

  function StatusPill(props) {
    var tone = props.tone || 'neutral';
    return h('span', { className: cx('ld-pill', 'ld-pill-' + tone, props.className) },
      h('span', { className: 'ld-pill-dot', 'aria-hidden': 'true' }), props.children);
  }

  function AppBar(props) {
    return h('header', { className: cx('ld-appbar', props.className) },
      h('div', { className: 'ld-appbar-id' },
        h('span', { className: 'ld-appbar-logo' }, h(Mark, { size: 30 })),
        h('div', { className: 'ld-appbar-names' },
          h('span', { className: 'ld-appbar-title' },
            h('span', { className: 'ld-wordmark' }, 'lightday'),
            props.appName ? h('span', { className: 'ld-appbar-app' }, ' · ' + props.appName) : null),
          props.subtitle ? h('span', { className: 'ld-appbar-sub' }, props.subtitle) : null)),
      h('div', { className: 'ld-appbar-end' },
        props.status ? h(StatusPill, { tone: props.status.tone }, props.status.label) : null,
        props.actions || null));
  }

  function MicButton(props) {
    var rec = !!props.recording;
    var rest = omit(props, ['recording', 'onToggle', 'className', 'label']);
    return h('button', Object.assign({ type: 'button' }, rest, {
      className: cx('ld-mic', rec && 'ld-mic-rec', props.className),
      'aria-pressed': rec ? 'true' : 'false',
      'aria-label': rec ? 'Stop dictation' : 'Start dictation',
      onClick: props.onToggle || props.onClick
    }), Icon(rec ? 'stop' : 'mic', 32), h('span', { className: 'ld-mic-label' }, props.label || (rec ? 'Stop' : 'Dictate')));
  }

  var fieldSeq = 0;
  function Field(props) {
    var idRef = React.useRef(null);
    if (!idRef.current) idRef.current = props.id || 'ld-field-' + (++fieldSeq);
    var id = idRef.current;
    var rest = omit(props, ['label', 'hint', 'className', 'id', 'type']);
    return h('div', { className: cx('ld-field', props.className) },
      h('label', { className: 'ld-field-label', htmlFor: id }, props.label),
      h('input', Object.assign({ id: id, type: props.type || 'text', className: 'ld-input', 'aria-describedby': props.hint ? id + '-hint' : undefined }, rest)),
      props.hint ? h('span', { id: id + '-hint', className: 'ld-field-hint' }, props.hint) : null);
  }

  function Card(props) {
    return h('section', { className: cx('ld-card', props.tone === 'sunk' && 'ld-card-sunk', props.className), 'aria-label': props.title || undefined },
      props.title ? h('h2', { className: 'ld-card-title' }, props.title) : null,
      props.children);
  }

  function ListRow(props) {
    return h('button', { type: 'button', className: cx('ld-row', props.selected && 'ld-row-on', props.className), 'aria-current': props.selected ? 'true' : undefined, onClick: props.onClick },
      h('span', { className: 'ld-row-text' },
        h('span', { className: 'ld-row-title' }, props.title),
        props.meta ? h('span', { className: 'ld-row-meta' }, props.meta) : null),
      props.tag ? h('span', { className: 'ld-row-tag' }, props.tag) : null);
  }

  function SpokenGuide(props) {
    var steps = props.steps || [];
    var active = props.active || 0;
    return h('section', { className: cx('ld-card', 'ld-guide', props.className), 'aria-label': props.title || 'What to say' },
      h('h2', { className: 'ld-card-title' }, props.title || 'What to say'),
      h('ol', { className: 'ld-guide-list' }, steps.map(function (s, i) {
        var n = i + 1;
        var state = n === active ? 'on' : (active && n < active ? 'done' : '');
        return h('li', { key: n, className: cx('ld-guide-step', state && 'ld-guide-' + state), 'aria-current': state === 'on' ? 'step' : undefined },
          h('span', { className: 'ld-guide-n' }, n),
          h('span', { className: 'ld-guide-text' },
            h('span', { className: 'ld-guide-say' }, s.say), ' ',
            s.example ? h('span', { className: 'ld-guide-ex' }, s.example) : null));
      })));
  }

  function PaperSheet(props) {
    var fields = props.fields || [];
    var sections = props.sections || [];
    return h('article', { className: cx('ld-sheet', props.className) },
      h('header', { className: 'ld-sheet-head' },
        h('div', { className: 'ld-sheet-letterhead' }, props.letterhead || '[Letterhead prints here — add it in Profile]'),
        props.title ? h('h1', { className: 'ld-sheet-title' }, props.title) : null),
      fields.length ? h('dl', { className: 'ld-sheet-fields' }, fields.map(function (f, i) {
        return h('div', { key: i, className: 'ld-sheet-field' },
          h('dt', null, f.label),
          h('dd', { className: f.value ? '' : 'ld-sheet-blank' }, f.value || '—'));
      })) : null,
      h('div', { className: 'ld-sheet-sections' }, sections.map(function (s, i) {
        return h('section', { key: i, className: cx('ld-sheet-sec', s.listening && 'ld-sheet-sec-on') },
          h('div', { className: 'ld-sheet-sec-head' },
            h('h3', null, s.heading),
            s.listening ? h('span', { className: 'ld-listening' }, 'Listening') : null),
          s.text ? h('p', null, s.text) : h('p', { className: 'ld-sheet-empty' }, props.emptyText || 'Not dictated yet'));
      })),
      props.children || null);
  }

  function AppTile(props) {
    return h('a', { className: cx('ld-tile', props.className), href: props.href || '#' },
      h('span', { className: 'ld-tile-top' },
        h('span', { className: 'ld-tile-icon', 'aria-hidden': 'true' }, props.initial || (props.name || '?').charAt(0)),
        props.status ? h(StatusPill, { tone: props.status.tone }, props.status.label) : null),
      h('span', { className: 'ld-tile-name' }, props.name),
      props.job ? h('span', { className: 'ld-tile-job' }, props.job) : null,
      h('span', { className: 'ld-tile-foot' },
        props.price ? h('span', { className: 'ld-tile-price' }, props.price) : h('span', null),
        h('span', { className: 'ld-tile-open' }, 'Open', Icon('arrow', 16))));
  }

  var api = { AppBar: AppBar, Button: Button, MicButton: MicButton, StatusPill: StatusPill, Field: Field, Card: Card, ListRow: ListRow, SpokenGuide: SpokenGuide, PaperSheet: PaperSheet, AppTile: AppTile, Mark: Mark };
  window.Lightday = Object.assign(window.Lightday || {}, api);
})();
