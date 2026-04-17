/**
 * Sauvage Booking Chatbot Widget
 * --------------------------------
 * Drop one <script> tag into your Shopify theme and the floating
 * booking assistant appears automatically.
 *
 * Usage:
 *   <script src="https://booking.selectionsauvage.nl/widget.js" defer></script>
 */

(function () {
  // Load Flatpickr CSS for calendar widget
  var flatpickrCss = document.createElement('link');
  flatpickrCss.rel = 'stylesheet';
  flatpickrCss.href = 'https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.css';
  document.head.appendChild(flatpickrCss);
  
  // Load Flatpickr JS for calendar widget
  var flatpickrScript = document.createElement('script');
  flatpickrScript.src = 'https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.js';
  flatpickrScript.onload = function() {
    window.FlatpickrLoaded = true;
  };
  document.head.appendChild(flatpickrScript);
  const API = "https://sauvage.amsterdam";
  const STAGES = ["Event details", "Your info", "Space & add-ons", "Quote", "Payment"];
  let sessionId = null;
  let currentStage = 0;
  let open = false;
  let _pickerConfirm = null;        // set when calendar is open, cleared on confirm/remove
  let _paymentPollTimer = null;     // interval ID while polling for deposit confirmation
  let _pendingCheckoutUrl = null;   // checkout URL returned by backend, used by pay button
  const _shownWidgets = new Set();  // tracks widget types shown this session — each fires once

  // ── Styles ────────────────────────────────────────────────────────────────
  const css = `
    #sv-widget * { box-sizing: border-box; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; text-align: left; }

    #sv-bubble {
      position: fixed; bottom: 24px; right: 24px; z-index: 9999;
      width: 56px; height: 56px; border-radius: 50%;
      background: #1a1a1a; color: #fff; border: none; cursor: pointer;
      box-shadow: 0 4px 16px rgba(0,0,0,0.25);
      display: flex; align-items: center; justify-content: center;
      font-size: 24px; transition: transform 0.2s;
    }
    #sv-bubble:hover { transform: scale(1.08); }

    #sv-panel {
      position: fixed; bottom: 92px; right: 24px; z-index: 9998;
      width: 360px; height: 640px; max-height: 88vh;
      background: #fff; border-radius: 16px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.18);
      display: flex; flex-direction: column;
      overflow: hidden; transition: opacity 0.2s, transform 0.2s;
      opacity: 0; transform: translateY(12px) scale(0.97); pointer-events: none;
    }
    #sv-panel.sv-open { opacity: 1; transform: translateY(0) scale(1); pointer-events: all; }

    #sv-header {
      background: #1a1a1a; color: #fff; padding: 14px 16px 10px;
      flex-shrink: 0;
    }
    #sv-header h3 { margin: 0 0 2px; font-size: 15px; font-weight: 600; color: #fff; }
    #sv-header p { margin: 0; font-size: 12px; opacity: 0.65; }

    #sv-progress { padding: 10px 16px 0; flex-shrink: 0; }
    #sv-progress-bar-bg {
      background: #e8e8e8; border-radius: 4px; height: 4px; margin-bottom: 6px;
    }
    #sv-progress-bar {
      background: #1a1a1a; height: 4px; border-radius: 4px;
      width: 0%; transition: width 0.4s ease;
    }
    #sv-stage-label { font-size: 11px; color: #888; }

    #sv-messages {
      flex: 1; overflow-y: auto; padding: 14px 14px 8px;
      display: flex; flex-direction: column; gap: 10px;
    }

    .sv-msg { max-width: 82%; line-height: 1.45; font-size: 14px; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word; min-width: 0; }
    .sv-msg-bot {
      background: #f2f2f2; color: #1a1a1a;
      padding: 10px 13px; border-radius: 14px 14px 14px 3px;
      align-self: flex-start;
    }
    .sv-msg-user {
      background: #1a1a1a; color: #fff;
      padding: 10px 13px; border-radius: 14px 14px 3px 14px;
      align-self: flex-end;
    }
    .sv-typing {
      background: #f2f2f2; padding: 10px 14px; border-radius: 14px 14px 14px 3px;
      align-self: flex-start; display: flex; gap: 4px; align-items: center;
    }
    .sv-dot {
      width: 6px; height: 6px; background: #999; border-radius: 50%;
      animation: sv-bounce 1.2s infinite;
    }
    .sv-dot:nth-child(2) { animation-delay: 0.2s; }
    .sv-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes sv-bounce {
      0%, 80%, 100% { transform: translateY(0); }
      40% { transform: translateY(-5px); }
    }

    #sv-input-area {
      padding: 10px 12px 12px; border-top: 1px solid #ececec; flex-shrink: 0;
      display: flex; gap: 8px; align-items: flex-end;
    }
    #sv-input {
      flex: 1; border: 1px solid #ddd; border-radius: 10px;
      padding: 9px 12px; font-size: 14px; resize: none;
      outline: none; line-height: 1.4; max-height: 100px;
      font-family: inherit;
    }
    #sv-input:focus { border-color: #1a1a1a; }
    #sv-send {
      background: #1a1a1a; color: #fff; border: none; border-radius: 10px;
      padding: 9px 14px; cursor: pointer; font-size: 14px; font-weight: 500;
      white-space: nowrap;
    }
    #sv-send:hover { background: #333; }
    #sv-send:disabled { opacity: 0.4; cursor: default; }

    /* Attribution radio widget */
    .sv-radio-wrap { padding: 2px 0 4px; }
    .sv-radio-opt {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 12px; border-radius: 9px; cursor: pointer; margin-bottom: 4px;
      border: 1.5px solid #ececec; background: #fafafa;
      transition: border-color 0.12s, background 0.12s;
      font-size: 13px; font-weight: 500; color: #1a1a1a;
    }
    .sv-radio-opt:hover { border-color: #c0c0c0; background: #f3f3f3; }
    .sv-radio-opt.sv-radio-sel { border-color: #1a1a1a; background: #1a1a1a; color: #fff; }
    .sv-radio-circle {
      width: 17px; height: 17px; border-radius: 50%; border: 1.5px solid #d0d0d0;
      flex-shrink: 0; display: flex; align-items: center; justify-content: center;
      transition: border-color 0.12s, background 0.12s;
    }
    .sv-radio-sel .sv-radio-circle { border-color: #fff; background: #fff; }
    .sv-radio-sel .sv-radio-circle::after {
      content: ''; width: 7px; height: 7px; border-radius: 50%; background: #1a1a1a; display: block;
    }
    .sv-radio-other-input {
      width: 100%; border: 1.5px solid #e0e0e0; border-radius: 8px;
      padding: 7px 10px; font-size: 13px; font-family: inherit;
      margin-bottom: 5px; outline: none; display: none;
    }
    .sv-radio-other-input:focus { border-color: #1a1a1a; }
    .sv-radio-confirm {
      width: 100%; margin-top: 2px; background: #1a1a1a; color: #fff; border: none;
      border-radius: 8px; padding: 8px 12px; font-size: 12px; font-weight: 600;
      cursor: pointer; font-family: inherit; transition: background 0.15s; outline: none;
    }
    .sv-radio-confirm:hover { background: #333; }
    .sv-radio-confirm:disabled { opacity: 0.3; cursor: default; }

    /* Contact widget */
    .sv-contact-wrap { padding: 1px 0 4px; }
    .sv-contact-field { margin-bottom: 4px; }
    .sv-contact-lbl {
      font-size: 8px; font-weight: 700; color: #bbb; display: block;
      margin-bottom: 2px; letter-spacing: 0.07em; text-transform: uppercase;
    }
    .sv-contact-row { display: flex; align-items: center; gap: 5px; }
    .sv-contact-input {
      flex: 1; border: 1.5px solid #e0e0e0; border-radius: 7px;
      padding: 5px 9px; font-size: 12px; font-family: inherit;
      outline: none; transition: border-color 0.15s, box-shadow 0.15s; color: #1a1a1a;
      background: #fff;
    }
    .sv-contact-input:focus { border-color: #1a1a1a; box-shadow: 0 0 0 2px rgba(26,26,26,0.06); }
    .sv-contact-input.sv-input-ok { border-color: #22c55e; }
    .sv-check {
      width: 18px; height: 18px; border-radius: 50%;
      border: 1.5px solid #e0e0e0; display: flex; align-items: center; justify-content: center;
      font-size: 9px; font-weight: 800; color: transparent; flex-shrink: 0;
      transition: border-color 0.2s, background 0.2s, color 0.2s, transform 0.15s;
      background: transparent;
    }
    .sv-check.sv-check-ok {
      border-color: #22c55e; background: #22c55e; color: #fff;
      transform: scale(1.08);
    }
    .sv-contact-submit {
      width: 100%; margin-top: 4px; background: #1a1a1a; color: #fff;
      border: none; border-radius: 7px; padding: 7px 12px; font-size: 11px;
      font-weight: 600; cursor: pointer; font-family: inherit; letter-spacing: 0.01em;
      transition: background 0.15s; outline: none;
    }
    .sv-contact-submit:not(:disabled):hover { background: #333; }
    .sv-contact-submit:disabled { opacity: 0.3; cursor: default; }

    /* Customer type toggle */
    /* ── Event type picker ── */
    .sv-etype-wrap { padding: 2px 0 6px; }
    .sv-etype-grid {
      display: grid; grid-template-columns: 1fr 1fr; gap: 7px; margin-top: 4px;
    }
    .sv-etype-btn {
      padding: 10px 8px; border-radius: 10px;
      border: 1.5px solid #e0e0e0; background: #fafafa;
      font-size: 12px; font-weight: 600; color: #999;
      cursor: pointer; font-family: inherit; text-align: center;
      transition: border-color 0.15s, color 0.15s, background 0.15s, transform 0.1s;
      outline: none; line-height: 1.3;
    }
    .sv-etype-btn .sv-etype-icon { font-size: 18px; display: block; margin-bottom: 4px; }
    .sv-etype-btn:hover { border-color: #1a1a1a; color: #1a1a1a; background: #fff; }
    .sv-etype-btn.sv-etype-sel { border-color: #1a1a1a; background: #1a1a1a; color: #fff; }
    .sv-etype-other-row { margin-top: 7px; display: flex; gap: 7px; }
    .sv-etype-other-input {
      flex: 1; border: 1.5px solid #e0e0e0; border-radius: 10px; padding: 8px 10px;
      font-size: 13px; font-family: inherit; outline: none; background: #fafafa;
      transition: border-color 0.15s;
    }
    .sv-etype-other-input:focus { border-color: #1a1a1a; background: #fff; }
    .sv-etype-confirm {
      background: #1a1a1a; color: #fff; border: none; border-radius: 10px;
      padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer;
      font-family: inherit; white-space: nowrap; outline: none; transition: background 0.15s;
    }
    .sv-etype-confirm:hover { background: #333; }

    .sv-ctype-wrap { padding: 2px 0 6px; }
    .sv-ctype-row { display: flex; gap: 8px; margin-top: 4px; }
    .sv-ctype-btn {
      flex: 1; padding: 14px 8px; border-radius: 12px;
      border: 1.5px solid #e0e0e0; background: #fafafa;
      font-size: 13px; font-weight: 600; color: #aaa;
      cursor: pointer; font-family: inherit; text-align: center;
      transition: border-color 0.15s, color 0.15s, background 0.15s, transform 0.1s;
      outline: none; line-height: 1.3;
    }
    .sv-ctype-icon { font-size: 20px; display: block; margin-bottom: 5px; }
    .sv-ctype-btn:hover { border-color: #1a1a1a; color: #1a1a1a; background: #fff; }
    .sv-ctype-btn:active { transform: scale(0.96); background: #1a1a1a; color: #fff; border-color: #1a1a1a; }

    /* PDF export button */
    .sv-pdf-btn {
      display: inline-flex; align-items: center; gap: 5px;
      background: none; border: 1.5px solid #c0c0c0; border-radius: 7px;
      padding: 5px 11px; font-size: 11px; font-weight: 600; color: #888;
      cursor: pointer; font-family: inherit; margin-top: 5px;
      transition: border-color 0.15s, color 0.15s; letter-spacing: 0.01em;
      align-self: flex-start;
    }
    .sv-pdf-btn:hover { border-color: #1a1a1a; color: #1a1a1a; }

    /* Quick reply buttons */
    .sv-quick-replies {
      display: flex; flex-wrap: wrap; gap: 7px;
      padding: 4px 0 10px;
    }
    .sv-qr-btn {
      background: #fff; color: #1a1a1a;
      border: 1.5px solid #1a1a1a; border-radius: 20px;
      padding: 6px 14px; font-size: 13px; cursor: pointer;
      font-family: inherit; transition: background 0.15s, color 0.15s;
      white-space: nowrap; line-height: 1.3;
    }
    .sv-qr-btn:hover { background: #1a1a1a; color: #fff; }

    /* ── Add-ons widget ── */
    .sv-addons-wrap { padding: 2px 0 6px; }
    .sv-addon-row {
      display: flex; align-items: center; justify-content: space-between; gap: 6px;
      padding: 6px 9px; border-radius: 8px; margin-bottom: 3px;
      border: 1.5px solid #ececec; background: #fafafa; cursor: pointer;
      transition: border-color 0.12s, background 0.12s;
    }
    .sv-addon-row:hover { border-color: #c8c8c8; }
    .sv-addon-row.sv-aon { border-color: #1a1a1a; background: #1a1a1a; }
    .sv-addon-left { display: flex; align-items: center; gap: 7px; flex: 1; min-width: 0; }
    .sv-addon-chk {
      width: 14px; height: 14px; border-radius: 3px; border: 1.5px solid #ccc;
      flex-shrink: 0; display: flex; align-items: center; justify-content: center;
      font-size: 9px; font-weight: 900; color: transparent; transition: all 0.12s;
    }
    .sv-aon .sv-addon-chk { border-color: #fff; background: #fff; color: #1a1a1a; }
    .sv-addon-name { font-size: 11px; font-weight: 600; color: #1a1a1a; line-height: 1.2; }
    .sv-aon .sv-addon-name { color: #fff; }
    .sv-addon-sub { font-size: 9px; color: #666; line-height: 1; margin-top: 1px; }
    .sv-aon .sv-addon-sub { color: rgba(255,255,255,0.7); }
    .sv-addon-right { display: flex; align-items: center; gap: 5px; flex-shrink: 0; }
    .sv-addon-qrow { display: flex; align-items: center; gap: 2px; }
    .sv-addon-qbtn {
      background: rgba(255,255,255,0.18); border: none; color: #fff; cursor: pointer;
      font-size: 13px; padding: 1px 5px; border-radius: 3px; font-family: inherit;
      line-height: 1; outline: none; transition: background 0.1s;
    }
    .sv-addon-qbtn:hover { background: rgba(255,255,255,0.35); }
    .sv-addon-qval { font-size: 10px; font-weight: 700; color: #fff; min-width: 22px; text-align: center; }
    .sv-addon-price { font-size: 11px; font-weight: 700; color: #888; white-space: nowrap; }
    .sv-aon .sv-addon-price { color: rgba(255,255,255,0.9); }
    .sv-addon-footer { border-top: 1px solid #f0f0f0; margin-top: 4px; padding-top: 6px; }
    .sv-addon-total-row {
      display: flex; justify-content: space-between; align-items: baseline;
      margin-bottom: 5px;
    }
    .sv-addon-total-lbl { font-size: 10px; color: #666; }
    .sv-addon-total-val { font-size: 15px; font-weight: 800; color: #1a1a1a; }
    .sv-addon-note {
      font-size: 9px; color: #555; background: #f5f5f5; border-radius: 5px;
      padding: 5px 7px; margin: 4px 0 2px; line-height: 1.4;
    }
    .sv-addon-confirm {
      width: 100%; background: #1a1a1a; color: #fff; border: none;
      border-radius: 8px; padding: 8px 12px; font-size: 12px; font-weight: 600;
      cursor: pointer; font-family: inherit; transition: background 0.15s; outline: none;
    }
    .sv-addon-confirm:hover { background: #333; }
    /* Tooltip */
    .sv-addon-tip {
      display: inline-flex; align-items: center; justify-content: center;
      width: 13px; height: 13px; border-radius: 50%; border: 1.5px solid #bbb;
      font-size: 8px; font-weight: 700; color: #888; cursor: default;
      margin-left: 4px; vertical-align: middle; flex-shrink: 0; position: relative;
      user-select: none;
    }
    .sv-aon .sv-addon-tip { border-color: rgba(255,255,255,0.5); color: rgba(255,255,255,0.7); }
    .sv-addon-tip:hover::after {
      content: attr(data-tip);
      position: absolute; left: 50%; bottom: calc(100% + 6px);
      transform: translateX(-50%);
      background: #222; color: #fff; font-size: 10px; font-weight: 400;
      border-radius: 5px; padding: 5px 9px; white-space: nowrap;
      pointer-events: none; z-index: 99;
      box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    }
    .sv-addon-tip:hover::before {
      content: "";
      position: absolute; left: 50%; bottom: calc(100% + 2px);
      transform: translateX(-50%);
      border: 4px solid transparent; border-top-color: #222;
      pointer-events: none; z-index: 99;
    }

    /* ── Arrival time picker ── */
    .sv-arrival-wrap {
      display: flex; align-items: center; gap: 8px; padding: 6px 0 6px;
    }
    .sv-arrival-lbl { font-size: 11px; color: #999; white-space: nowrap; flex-shrink: 0; }
    .sv-arrival-confirm {
      flex: 1; background: #1a1a1a; color: #fff; border: none; border-radius: 8px;
      padding: 6px 10px; font-size: 12px; font-weight: 600; cursor: pointer;
      font-family: inherit; transition: background 0.15s; outline: none; white-space: nowrap;
    }
    .sv-arrival-confirm:hover { background: #333; }

    /* ── T&C Checkbox Widget ── */
    .sv-tandc-wrap {
      background: #fff; border: 1px solid #e8e8e8; border-radius: 12px;
      padding: 12px 14px; margin: 4px 0 6px;
    }
    .sv-tandc-label {
      display: flex; align-items: flex-start; gap: 10px; cursor: pointer;
      font-size: 13px; color: #1a1a1a; line-height: 1.4; margin-bottom: 10px;
    }
    .sv-tandc-box {
      width: 18px; height: 18px; border: 2px solid #ccc; border-radius: 4px;
      flex-shrink: 0; margin-top: 1px; display: flex; align-items: center;
      justify-content: center; transition: all 0.15s; background: #fff;
    }
    .sv-tandc-box.checked { background: #1a1a1a; border-color: #1a1a1a; color: #fff; }
    .sv-tandc-link { color: #1a1a1a; font-weight: 600; text-decoration: underline; }
    .sv-tandc-btn {
      width: 100%; background: #1a1a1a; color: #fff; border: none; border-radius: 8px;
      padding: 9px 14px; font-size: 13px; font-weight: 600; cursor: pointer;
      font-family: inherit; transition: background 0.15s; outline: none;
    }
    .sv-tandc-btn:disabled { background: #ccc; cursor: default; }
    .sv-tandc-btn:not(:disabled):hover { background: #333; }
    .sv-pay-btn {
      width: 100%; background: #1a1a1a; color: #fff; border: none; border-radius: 8px;
      padding: 11px 14px; font-size: 14px; font-weight: 700; cursor: pointer;
      font-family: inherit; transition: background 0.15s; outline: none;
      margin-top: 8px; display: flex; align-items: center; justify-content: center; gap: 6px;
    }
    .sv-pay-btn:disabled { background: #ccc; cursor: default; }
    .sv-pay-btn:not(:disabled):hover { background: #333; }
    .sv-pay-divider { border: none; border-top: 1px solid #f0f0f0; margin: 10px 0 2px; }

    /* ── Date / Time Picker ── */
    .sv-dt-picker {
      background: #fff; border: 1px solid #e8e8e8; border-radius: 12px;
      padding: 6px 5px 6px; margin: 2px 0 6px;
      user-select: none; box-sizing: border-box; width: 100%;
      box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }
    .sv-cal-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 3px; padding: 0 1px;
    }
    .sv-cal-title { font-size: 11px; font-weight: 700; color: #1a1a1a; letter-spacing: 0.01em; }
    .sv-cal-nav {
      background: #f5f5f5; border: none; border-radius: 4px;
      width: 20px; height: 20px; min-width: 20px; cursor: pointer; font-size: 11px;
      color: #1a1a1a; display: flex; align-items: center; justify-content: center;
      transition: background 0.12s, color 0.12s; outline: none; flex-shrink: 0;
    }
    .sv-cal-nav:hover { background: #1a1a1a; color: #fff; }
    .sv-cal-nav:active { transform: scale(0.9); }
    .sv-cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 0; }
    .sv-cal-dow {
      font-size: 7px; font-weight: 700; color: #bbb; text-align: center;
      padding: 0 0 1px; letter-spacing: 0.03em; text-transform: uppercase;
    }
    /* Day cell wrapper handles the range band */
    .sv-cal-day-wrap { position: relative; display: flex; align-items: center; justify-content: center; padding: 0; }
    .sv-cal-day-wrap.sv-range-mid  { background: #f0f0f0; }
    .sv-cal-day-wrap.sv-range-start { background: linear-gradient(to right, transparent 50%, #f0f0f0 50%); }
    .sv-cal-day-wrap.sv-range-end   { background: linear-gradient(to left,  transparent 50%, #f0f0f0 50%); }
    .sv-cal-day {
      border: none; background: none; border-radius: 50%; font-size: 9px;
      font-family: inherit; cursor: pointer; width: 20px; height: 20px;
      display: flex; align-items: center; justify-content: center;
      color: #1a1a1a; transition: background 0.12s, color 0.12s, transform 0.1s;
      outline: none; line-height: 1; flex-shrink: 0; position: relative; z-index: 1;
    }
    .sv-cal-day:not(:disabled):hover { background: #efefef; }
    .sv-cal-day:not(:disabled):active { transform: scale(0.88); }
    .sv-cal-day.sv-cal-selected { background: #1a1a1a; color: #fff; font-weight: 700; }
    .sv-cal-day.sv-cal-today { font-weight: 800; color: #1a1a1a; }
    .sv-cal-day.sv-cal-today::after {
      content: ''; position: absolute; bottom: 1px; left: 50%; transform: translateX(-50%);
      width: 2px; height: 2px; border-radius: 50%; background: currentColor;
    }
    .sv-cal-day.sv-cal-selected.sv-cal-today::after { background: #fff; }
    .sv-cal-day:disabled { color: #ddd; cursor: default; }
    /* Selected count bar */
    .sv-sel-bar {
      display: flex; align-items: center; justify-content: space-between;
      margin: 2px 1px 0; min-height: 10px;
    }
    .sv-sel-count { font-size: 9px; color: #888; }
    .sv-sel-clear {
      font-size: 9px; color: #1a1a1a; background: none; border: none;
      cursor: pointer; font-family: inherit; padding: 0; text-decoration: underline; outline: none;
    }
    /* Time section */
    .sv-time-section { margin-top: 5px; padding-top: 5px; border-top: 1px solid #f0f0f0; }
    .sv-time-header {
      display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;
    }
    .sv-time-section-label {
      font-size: 7px; font-weight: 700; color: #c0c0c0; letter-spacing: 0.1em;
      text-transform: uppercase;
    }
    /* Per-day toggle pill */
    .sv-time-toggle {
      display: flex; border: 1.5px solid #e0e0e0; border-radius: 6px; overflow: hidden;
    }
    .sv-tt-opt {
      background: none; border: none; cursor: pointer; padding: 3px 8px;
      font-size: 10px; font-weight: 600; color: #999; font-family: inherit;
      letter-spacing: 0.02em; transition: background 0.12s, color 0.12s; outline: none;
      white-space: nowrap;
    }
    .sv-tt-opt.sv-tt-active { background: #1a1a1a; color: #fff; }
    .sv-tt-opt:not(.sv-tt-active):hover { background: #f5f5f5; color: #1a1a1a; }
    .sv-time-row { display: flex; align-items: center; gap: 5px; margin-bottom: 2px; }
    .sv-time-lbl { font-size: 9px; color: #999; width: 24px; flex-shrink: 0; }
    /* Per-day date label */
    .sv-pd-lbl {
      font-size: 8px; font-weight: 700; color: #555; width: 42px; flex-shrink: 0;
      letter-spacing: 0.01em;
    }
    .sv-stepper {
      display: inline-flex; align-items: center; border: 1.5px solid #e0e0e0;
      border-radius: 5px; overflow: hidden; background: #fff;
    }
    .sv-step-btn {
      background: none; border: none; cursor: pointer; padding: 3px 6px;
      font-size: 13px; font-weight: 300; color: #1a1a1a; font-family: inherit;
      line-height: 1; transition: background 0.1s; outline: none;
    }
    .sv-step-btn:hover { background: #f5f5f5; }
    .sv-step-btn:active { background: #1a1a1a; color: #fff; }
    .sv-step-val {
      font-size: 11px; font-weight: 700; color: #1a1a1a; min-width: 32px;
      text-align: center; letter-spacing: 0.02em;
    }
    .sv-duration {
      font-size: 9px; color: #bbb; margin-left: 1px;
      background: #f5f5f5; border-radius: 3px; padding: 1px 3px;
    }
    .sv-dt-confirm {
      width: 100%; margin-top: 5px; background: #1a1a1a; color: #fff;
      border: none; border-radius: 7px; padding: 7px 8px; font-size: 10px;
      font-weight: 700; cursor: pointer; font-family: inherit; letter-spacing: 0.01em;
      transition: background 0.15s, transform 0.1s; line-height: 1.4; outline: none;
      box-sizing: border-box;
    }
    .sv-dt-confirm:not(:disabled):hover { background: #333; }
    .sv-dt-confirm:not(:disabled):active { transform: scale(0.98); }
    .sv-dt-confirm:disabled { opacity: 0.3; cursor: default; }

    @media (max-width: 420px) {
      #sv-panel { width: calc(100vw - 24px); right: 12px; bottom: 80px; }
      #sv-bubble { right: 12px; bottom: 12px; }
    }
  `;

  // ── DOM helpers ───────────────────────────────────────────────────────────
  function injectStyles() {
    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
  }

  function buildWidget() {
    const wrap = document.createElement("div");
    wrap.id = "sv-widget";
    wrap.innerHTML = `
      <button id="sv-bubble" aria-label="Book Sauvage">💬</button>
      <div id="sv-panel" role="dialog" aria-label="Sauvage Booking Assistant">
        <div id="sv-header">
          <h3>Sauvage Booking</h3>
          <p>Potgieterstraat 47H · Amsterdam</p>
        </div>
        <div id="sv-progress">
          <div id="sv-progress-bar-bg"><div id="sv-progress-bar"></div></div>
          <div id="sv-stage-label">Step 1 of 5 — Event details</div>
        </div>
        <div id="sv-messages"></div>
        <div id="sv-input-area">
          <textarea id="sv-input" rows="1" placeholder="Type a message…"></textarea>
          <button id="sv-send">Send</button>
        </div>
      </div>
    `;
    document.body.appendChild(wrap);
  }

  function addMessage(text, role) {
    const msgs = document.getElementById("sv-messages");
    const div = document.createElement("div");
    div.className = `sv-msg sv-msg-${role}`;
    // Render markdown-lite: bold, links, line breaks
    div.innerHTML = text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      // Named markdown links [text](url) — convert first so bare-URL pass doesn't double-link
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener" ' +
        'style="color:#1a1a1a;font-weight:600;text-decoration:underline;text-underline-offset:2px;">$1</a>')
      // Bare URLs not already inside an href — auto-linkify
      .replace(/(?<!href=")(https?:\/\/[^\s<>")\]]+)/g,
        '<a href="$1" target="_blank" rel="noopener" ' +
        'style="color:#1a1a1a;font-weight:600;text-decoration:underline;text-underline-offset:2px;">$1</a>')
      .replace(/\n/g, "<br>");
    msgs.appendChild(div);
    if (role === "user") {
      // User messages: scroll to bottom so the sent message is visible
      msgs.scrollTop = msgs.scrollHeight;
    } else {
      // Bot messages: scroll so the TOP of the response is visible,
      // letting the user read naturally downward
      requestAnimationFrame(function() {
        var msgsRect = msgs.getBoundingClientRect();
        var divRect  = div.getBoundingClientRect();
        msgs.scrollTop = msgs.scrollTop + (divRect.top - msgsRect.top) - 10;
      });
    }
    return div;
  }

  function showTyping() {
    const msgs = document.getElementById("sv-messages");
    const div = document.createElement("div");
    div.className = "sv-typing";
    div.id = "sv-typing";
    div.innerHTML = `<div class="sv-dot"></div><div class="sv-dot"></div><div class="sv-dot"></div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function hideTyping() {
    const el = document.getElementById("sv-typing");
    if (el) el.remove();
  }

  function updateProgress(stage) {
    currentStage = Math.min(stage, STAGES.length - 1);
    const pct = ((currentStage) / (STAGES.length - 1)) * 100;
    document.getElementById("sv-progress-bar").style.width = pct + "%";
    document.getElementById("sv-stage-label").textContent =
      `Step ${currentStage + 1} of ${STAGES.length} — ${STAGES[currentStage]}`;
  }

  // Detect stage from bot response text
  function detectStage(text) {
    const t = text.toLowerCase();
    if (t.includes("payment link") || t.includes("deposit link") || t.includes("invoice")) return 4;
    if (t.includes("here's your quote") || t.includes("total incl vat") || t.includes("deposit to confirm")) return 3;
    if (t.includes("add-on") || t.includes("glassware") || t.includes("staff") || t.includes("music")) return 2;
    if (t.includes("name") || t.includes("email") || t.includes("phone") || t.includes("contact")) return 1;
    return currentStage;
  }

  function showQuickReplies(options) {
    const msgs = document.getElementById("sv-messages");
    const wrap = document.createElement("div");
    wrap.className = "sv-quick-replies";
    options.forEach(function(opt) {
      const btn = document.createElement("button");
      btn.className = "sv-qr-btn";
      btn.textContent = opt;
      btn.addEventListener("click", function() {
        wrap.remove();
        sendMessage(opt);
      });
      wrap.appendChild(btn);
    });
    msgs.appendChild(wrap);
    msgs.scrollTop = msgs.scrollHeight;
  }

  // Detect if message is a quote
  function isQuoteMessage(text) {
    const t = text.toLowerCase();
    return (t.includes("total incl vat") || t.includes("deposit to confirm")) &&
           (t.includes("quote") || t.includes("€"));
  }

  // Detect if the bot has just sent a payment link (Shopify invoice or static fallback)
  function hasPaymentLink(text) {
    return text.includes("selectionsauvage.nl/products/event-deposit") ||
           text.includes("myshopify.com") ||
           text.includes("invoice_url") ||
           (text.toLowerCase().includes("pay deposit") && text.includes("http"));
  }

  // Poll /chat/payment-status until Airtable confirms the deposit is paid,
  // then auto-send a message so the bot continues the flow.
  var _pollCount = 0;
  var _POLL_MAX  = 50; // ~5 minutes at 6s intervals

  function startPaymentPolling() {
    if (_paymentPollTimer) return; // already polling
    if (!sessionId) return;
    _pollCount = 0;
    console.log("[Sauvage] Payment polling started for session", sessionId);

    _paymentPollTimer = setInterval(async function() {
      _pollCount++;
      if (_pollCount > _POLL_MAX) {
        stopPaymentPolling();
        console.log("[Sauvage] Payment polling timed out after " + _POLL_MAX + " checks");
        return;
      }
      try {
        const r = await fetch(API + "/chat/payment-status/" + sessionId);
        if (!r.ok) return;
        const data = await r.json();
        if (data.status === "confirmed") {
          stopPaymentPolling();
          console.log("[Sauvage] Payment confirmed — continuing flow");
          // Track conversion: booking payment completed
          if (window.gtag) {
            gtag('event', 'booking_payment_completed', {
              'event_category': 'booking',
              'event_label': 'deposit_paid',
              'value': 1,
              'currency': 'EUR'
            });
          }
          // Advance progress bar to Payment step
          updateProgress(4);
          sendMessage("Payment confirmed \u2705 \u2014 deposit received.");
        }
      } catch (e) {
        // Network blip — keep polling silently
      }
    }, 6000);
  }

  function stopPaymentPolling() {
    if (_paymentPollTimer) {
      clearInterval(_paymentPollTimer);
      _paymentPollTimer = null;
    }
  }

  function addPdfExportButton(quoteText) {
    const msgs = document.getElementById("sv-messages");
    const btn = document.createElement("button");
    btn.className = "sv-pdf-btn";
    btn.innerHTML = "📄 Export as PDF";
    btn.addEventListener("click", function () {
      // Strip HTML tags from quoted text for plain text version
      var plain = quoteText
        .replace(/<strong>(.*?)<\/strong>/gi, "$1")
        .replace(/<a[^>]*>(.*?)<\/a>/gi, "$1")
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/<[^>]+>/g, "");
      var win = window.open("", "_blank", "width=600,height=800");
      if (!win) return;
      win.document.write(`<!DOCTYPE html><html><head>
        <meta charset="utf-8">
        <title>Sauvage Event Space — Quote</title>
        <style>
          body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                 max-width: 520px; margin: 40px auto; color: #1a1a1a;
                 font-size: 14px; line-height: 1.6; }
          h2 { font-size: 18px; margin-bottom: 4px; }
          .sub { color: #888; font-size: 12px; margin-bottom: 28px; }
          pre { white-space: pre-wrap; font-family: inherit; font-size: 14px;
                line-height: 1.7; }
          hr { border: none; border-top: 1px solid #e8e8e8; margin: 24px 0; }
          .footer { font-size: 11px; color: #aaa; margin-top: 32px; }
          @media print {
            body { margin: 20px; }
            button { display: none; }
          }
        </style>
      </head><body>
        <h2>Sauvage Event Space</h2>
        <div class="sub">Potgieterstraat 47H · Amsterdam · sauvage.amsterdam</div>
        <pre>${plain}</pre>
        <hr>
        <div class="footer">Generated by Sauvage Booking Assistant · ${new Date().toLocaleDateString("en-GB",{day:"numeric",month:"long",year:"numeric"})}</div>
        <script>setTimeout(function(){ window.print(); }, 400);<\/script>
      </body></html>`);
      win.document.close();
    });
    msgs.appendChild(btn);
  }

  // Scroll so the last bot message AND the widget below it are both visible
  function scrollToContext(msgs, widget) {
    requestAnimationFrame(function() {
      var msgsRect = msgs.getBoundingClientRect();
      var botMsgs = msgs.querySelectorAll('.sv-msg-bot');
      var anchor = botMsgs.length > 0 ? botMsgs[botMsgs.length - 1] : widget;
      var anchorRect = anchor.getBoundingClientRect();
      msgs.scrollTop = msgs.scrollTop + (anchorRect.top - msgsRect.top) - 10;
    });
  }

  // Check if bot is asking for attribution
  function isAskingAttribution(text) {
    const t = text.toLowerCase();
    return t.includes("how did you hear") || t.includes("hear about sauvage");
  }

  // Detect if user is asking to speak to a human
  function wantsHuman(text) {
    const t = text.toLowerCase();
    return (
      t.includes("talk to someone") ||
      t.includes("speak to someone") ||
      t.includes("speak to a person") ||
      t.includes("real person") ||
      t.includes("human") ||
      t.includes("speak to greg") ||
      t.includes("talk to greg") ||
      t.includes("contact you") ||
      t.includes("call someone") ||
      t.includes("whatsapp") ||
      t.includes("not helpful") ||
      t.includes("this isn't working") ||
      t.includes("this is not working") ||
      t.includes("forget it") ||
      t.includes("never mind")
    );
  }

  function showAttributionWidget() {
    var msgs = document.getElementById("sv-messages");
    var wrap = document.createElement("div");
    wrap.className = "sv-radio-wrap";

    // Values must match Airtable "Referral Source" single-select options verbatim
    // "Other…" triggers a free-text input; the raw text is sent to the bot, [ref:Other] to Airtable
    var OPTIONS = ["Greg","Dorian","Bart","Instagram","Google","Other…"];
    var selected = null;

    function render() {
      wrap.innerHTML = OPTIONS.map(function(opt) {
        var isSel = opt === selected;
        return '<div class="sv-radio-opt' + (isSel ? ' sv-radio-sel' : '') + '" data-val="' + opt + '">' +
          '<span>' + opt + '</span>' +
          '<span class="sv-radio-circle"></span>' +
        '</div>';
      }).join('') +
      '<input class="sv-radio-other-input" id="sv-attr-other" placeholder="Please specify…" style="display:' + (selected === 'Other…' ? 'block' : 'none') + '" />' +
      '<button class="sv-radio-confirm" id="sv-attr-ok"' + (selected ? '' : ' disabled') + '>Confirm</button>';

      wrap.querySelectorAll('.sv-radio-opt').forEach(function(el) {
        el.addEventListener('click', function() {
          selected = this.dataset.val;
          render();
          scrollToContext(msgs, wrap);
        });
      });

      var otherInput = wrap.querySelector('#sv-attr-other');
      if (otherInput) {
        otherInput.addEventListener('input', function() {
          var btn = wrap.querySelector('#sv-attr-ok');
          if (btn) btn.disabled = !this.value.trim();
        });
      }

      var okBtn = wrap.querySelector('#sv-attr-ok');
      if (okBtn) okBtn.addEventListener('click', submitAttribution);
    }

    function submitAttribution() {
      if (!selected) return;
      var value = selected === 'Other…'
        ? (wrap.querySelector('#sv-attr-other') ? wrap.querySelector('#sv-attr-other').value.trim() || 'Other' : 'Other')
        : selected;
      // Canonical tag for deterministic Airtable sync — backend parses [ref:...] directly
      var atValue = (selected === 'Other…') ? 'Other' : selected;
      _pickerConfirm = null;
      wrap.remove();
      sendMessage(value + ' [ref:' + atValue + ']');
    }

    render();
    msgs.appendChild(wrap);
    _pickerConfirm = submitAttribution;
    scrollToContext(msgs, wrap);
  }

  function isAskingContact(text) {
    const t = text.toLowerCase();
    // Guard: never fire if this is a customer type or confirmation message
    if (t.includes("private booking") || t.includes("business booking") ||
        t.includes("got it") || t.includes("perfect") || t.includes("noted")) return false;
    return (t.includes("name") && (t.includes("email") || t.includes("phone") || t.includes("reach"))) ||
           (t.includes("what's your name")) ||
           t.includes("best email") ||
           t.includes("reach you on") ||
           t.includes("how can we reach");
  }

  function showContactWidget() {
    if (_shownWidgets.has("contact")) return;
    _shownWidgets.add("contact");
    var msgs = document.getElementById("sv-messages");
    var wrap = document.createElement("div");
    wrap.className = "sv-contact-wrap";
    wrap.innerHTML =
      '<div class="sv-contact-field">' +
        '<label class="sv-contact-lbl">Name</label>' +
        '<div class="sv-contact-row">' +
          '<input class="sv-contact-input" id="sv-c-name" type="text" placeholder="Your full name" autocomplete="name" />' +
          '<span class="sv-check" id="sv-ck-name">✓</span>' +
        '</div>' +
      '</div>' +
      '<div class="sv-contact-field">' +
        '<label class="sv-contact-lbl">Email</label>' +
        '<div class="sv-contact-row">' +
          '<input class="sv-contact-input" id="sv-c-email" type="email" placeholder="you@example.com" autocomplete="email" />' +
          '<span class="sv-check" id="sv-ck-email">✓</span>' +
        '</div>' +
      '</div>' +
      '<div class="sv-contact-field">' +
        '<label class="sv-contact-lbl">Phone / WhatsApp</label>' +
        '<div class="sv-contact-row">' +
          '<input class="sv-contact-input" id="sv-c-phone" type="tel" placeholder="+31 6 …" autocomplete="tel" />' +
          '<span class="sv-check" id="sv-ck-phone">✓</span>' +
        '</div>' +
      '</div>' +
      '<button class="sv-contact-submit" id="sv-c-submit" disabled>Confirm details</button>';

    msgs.appendChild(wrap);

    function valEmail(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()); }
    function valPhone(v) { return v.trim().replace(/\s/g,'').length >= 7; }
    function valName(v)  { return v.trim().length >= 2; }

    function setField(inputId, checkId, ok) {
      var inp = document.getElementById(inputId);
      var chk = document.getElementById(checkId);
      if (!inp || !chk) return;
      inp.classList.toggle("sv-input-ok", ok);
      chk.classList.toggle("sv-check-ok", ok);
    }

    function update() {
      var nameOk  = valName(document.getElementById("sv-c-name").value);
      var emailOk = valEmail(document.getElementById("sv-c-email").value);
      var phoneOk = valPhone(document.getElementById("sv-c-phone").value);
      setField("sv-c-name",  "sv-ck-name",  nameOk);
      setField("sv-c-email", "sv-ck-email", emailOk);
      setField("sv-c-phone", "sv-ck-phone", phoneOk);
      var btn = document.getElementById("sv-c-submit");
      if (btn) btn.disabled = !(nameOk && emailOk && phoneOk);
    }

    ["sv-c-name","sv-c-email","sv-c-phone"].forEach(function(id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("input", update);
    });

    function submitContact() {
      var name  = document.getElementById("sv-c-name")  ? document.getElementById("sv-c-name").value.trim()  : "";
      var email = document.getElementById("sv-c-email") ? document.getElementById("sv-c-email").value.trim() : "";
      var phone = document.getElementById("sv-c-phone") ? document.getElementById("sv-c-phone").value.trim() : "";
      if (!valName(name) || !valEmail(email) || !valPhone(phone)) return;
      _pickerConfirm = null;
      wrap.remove();
      sendMessage(name + ", " + email + ", " + phone);
    }

    var submitBtn = document.getElementById("sv-c-submit");
    if (submitBtn) submitBtn.addEventListener("click", submitContact);
    _pickerConfirm = submitContact;
    scrollToContext(msgs, wrap);
  }

  // ── Event type picker ─────────────────────────────────────────────────────
  var EVENT_TYPES = [
    { label: "Birthday",     icon: "🎂" },
    { label: "Corporate",    icon: "🏢" },
    { label: "Pop-up",       icon: "🛍️" },
    { label: "Dinner",       icon: "🍽️" },
    { label: "Art Gallery",  icon: "🎨" },
    { label: "Wine Tasting", icon: "🍷" },
    { label: "Workshop",     icon: "🛠️" },
    { label: "Other",        icon: "✨" },
  ];

  function showEventTypeWidget() {
    var msgs = document.getElementById("sv-messages");
    // Don't show if already present
    if (document.querySelector(".sv-etype-wrap")) return;
    var wrap = document.createElement("div");
    wrap.className = "sv-etype-wrap";
    var selected = null;

    function render() {
      var gridBtns = EVENT_TYPES.map(function(et) {
        var sel = selected === et.label ? " sv-etype-sel" : "";
        return '<button class="sv-etype-btn' + sel + '" data-label="' + et.label + '">' +
          '<span class="sv-etype-icon">' + et.icon + '</span>' + et.label +
        '</button>';
      }).join('');

      var otherRow = selected === "Other"
        ? '<div class="sv-etype-other-row">' +
            '<input class="sv-etype-other-input" id="sv-etype-custom" placeholder="Describe your event…" />' +
            '<button class="sv-etype-confirm" id="sv-etype-ok">Go →</button>' +
          '</div>'
        : '';

      wrap.innerHTML = '<div class="sv-etype-grid">' + gridBtns + '</div>' + otherRow;

      wrap.querySelectorAll(".sv-etype-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
          selected = this.dataset.label;
          if (selected !== "Other") {
            _pickerConfirm = null;
            wrap.remove();
            sendMessage("I'm planning a " + selected + ".");
          } else {
            render();
            var inp = document.getElementById("sv-etype-custom");
            if (inp) inp.focus();
          }
        });
      });

      var okBtn = document.getElementById("sv-etype-ok");
      if (okBtn) {
        okBtn.addEventListener("click", function() {
          var val = (document.getElementById("sv-etype-custom") || {}).value || "";
          val = val.trim();
          if (!val) return;
          _pickerConfirm = null;
          wrap.remove();
          sendMessage("I'm planning a " + val + ".");
        });
      }
      var inp = document.getElementById("sv-etype-custom");
      if (inp) {
        inp.addEventListener("keydown", function(e) {
          if (e.key === "Enter") { if (okBtn) okBtn.click(); }
        });
      }
    }

    render();
    msgs.appendChild(wrap);
    scrollToContext(msgs, wrap);
  }

  function isAskingCustomerType(text) {
    const t = text.toLowerCase();
    // Never fire on confirmation sentences
    if (t.includes("confirmed") || t.includes("got it") || t.includes("great —") ||
        t.includes("noted") || t.includes("perfect")) return false;
    return (t.includes("private") && t.includes("business")) ||
           t.includes("booking as a") ||
           t.includes("individual or") ||
           t.includes("personal or business") ||
           t.includes("private booking or") ||
           t.includes("is this a private");
  }

  function showCustomerTypeToggle() {
    if (_shownWidgets.has("customer_type")) return;
    _shownWidgets.add("customer_type");
    var msgs = document.getElementById("sv-messages");
    var wrap = document.createElement("div");
    wrap.className = "sv-ctype-wrap";
    wrap.innerHTML =
      '<div class="sv-ctype-row">' +
        '<button class="sv-ctype-btn" id="sv-ct-private">' +
          '<span class="sv-ctype-icon">\uD83D\uDE4B</span>Private' +
        '</button>' +
        '<button class="sv-ctype-btn" id="sv-ct-business">' +
          '<span class="sv-ctype-icon">\uD83C\uDFE2</span>Business' +
        '</button>' +
      '</div>';
    msgs.appendChild(wrap);

    function pick(value) {
      wrap.remove();
      sendMessage(value);
    }

    document.getElementById("sv-ct-private").addEventListener("click", function() { pick("Private individual"); });
    document.getElementById("sv-ct-business").addEventListener("click", function() { pick("Business"); });
    scrollToContext(msgs, wrap);
  }

  // ── Add-ons widget ────────────────────────────────────────────────────────
  function isAskingAddons(text) {
    const t = text.toLowerCase();
    return (t.includes("add-on") || t.includes("addon")) &&
           (t.includes("available") || t.includes("select") || t.includes("include") || t.includes("like to add"));
  }

  function showAddonsWidget(opts) {
    if (_shownWidgets.has("addons")) return;
    _shownWidgets.add("addons");
    opts = opts || {};
    var msgs = document.getElementById("sv-messages");
    var wrap = document.createElement("div");
    wrap.className = "sv-addons-wrap";

    // at: exact Airtable "Add-Ons" multi-select option name — must match column options verbatim
    var ITEMS = [
      { id:"dishware",  name:"Dishware, cutlery & glass", sub:"25 pax",           price:25,  type:"flat",  at:"Dishware & Cutlery" },
      { id:"glass-st",  name:"Glassware — stem glasses",  sub:"25 pax · upgrade", price:35,  type:"flat",  at:"Stem Glassware" },
      { id:"staff",     name:"Staff support",             sub:"€35/hr · full event duration", price:35, type:"staff", at:"Staff Support" },
      { id:"cleanup",   name:"Event cleanup",             sub:"flat fee",          price:60,  type:"flat",  at:"Event Cleanup" },
      { id:"light-snacks", name:"Light snacks / Fento",    sub:"€5 per person",     price:5,   type:"pax",   at:"Light Snacks Fento", qty:10, tip:"2–3 light bites per person from Fento" },
      { id:"snacks",    name:"Snacks / Fento",            sub:"€10 per person",    price:10,  type:"pax",   at:"Snacks Fento", qty:10, tip:"4–5 pieces per person from Fento — fuller spread" },
      { id:"bar",       name:"Sommelier / barista service", sub:"€50/hr",          price:50,  type:"hr",    at:"Sommelier/Barista Service", qty:1 },
      { id:"projector", name:"Projector / screen",        sub:"flat fee",          price:25,  type:"flat",  at:"Projector/Display Screen" }
    ];

    var checked = {};
    var qty = {};
    ITEMS.forEach(function(i){ qty[i.id] = i.qty || 1; });

    // Pre-select items passed from backend (e.g. Fento when mentioned before widget appears)
    if (opts.preselect && Array.isArray(opts.preselect)) {
      opts.preselect.forEach(function(id) {
        checked[id] = true;
        // Use guest count for per-person items
        var item = ITEMS.find(function(it){ return it.id === id; });
        if (item && (item.type === "pax") && opts.pax && opts.pax > 0) {
          qty[id] = opts.pax;
        }
      });
    }

    function lineTotal(item) {
      if (!checked[item.id]) return 0;
      if (item.type === "flat") return item.price;
      if (item.type === "hr" || item.type === "pax") return item.price * qty[item.id];
      if (item.type === "staff") return 0; // calculated server-side from event duration
      return 0;
    }
    function grandTotal() { return ITEMS.reduce(function(s,i){ return s + lineTotal(i); }, 0); }
    function priceTag(item) {
      if (item.type === "consult") return "consult";
      if (item.type === "staff") return "€35/hr";
      if (!checked[item.id]) return "€" + item.price + (item.type === "hr" ? "/hr" : item.type === "pax" ? "/pp" : "");
      var t = lineTotal(item);
      return t > 0 ? "€" + t : "€" + item.price;
    }

    function footerTotal() {
      var nonStaff = grandTotal();
      var hasStaff = !!checked["staff"];
      if (hasStaff && nonStaff === 0) return '<span class="sv-addon-total-val" style="font-size:13px;color:#666;">staff · €35/hr (in quote)</span>';
      if (hasStaff) return '<span class="sv-addon-total-val">€' + nonStaff + ' <span style="font-size:11px;font-weight:500;color:#888;">+ staff (in quote)</span></span>';
      return '<span class="sv-addon-total-val">€' + nonStaff + '</span>';
    }

    function render() {
      var rows = [];
      ITEMS.forEach(function(item) {
        if (item.id === "staff") {
          rows.push('<div class="sv-addon-note">ℹ️ Without staff you manage bar, door &amp; logistics yourself.</div>');
        }
        var on = checked[item.id] ? " sv-aon" : "";
        var qrow = (checked[item.id] && (item.type === "hr" || item.type === "pax"))
          ? '<div class="sv-addon-qrow">' +
              '<button class="sv-addon-qbtn" data-id="' + item.id + '" data-dir="-1">−</button>' +
              '<span class="sv-addon-qval">' + qty[item.id] + (item.type === "hr" ? "h" : "p") + '</span>' +
              '<button class="sv-addon-qbtn" data-id="' + item.id + '" data-dir="1">+</button>' +
            '</div>'
          : '';
        var tipHtml = item.tip
          ? '<span class="sv-addon-tip" data-tip="' + item.tip + '" onclick="event.stopPropagation()">i</span>'
          : '';
        rows.push('<div class="sv-addon-row' + on + '" data-id="' + item.id + '">' +
          '<div class="sv-addon-left">' +
            '<div class="sv-addon-chk">✓</div>' +
            '<div><div class="sv-addon-name">' + item.name + tipHtml + '</div>' +
            '<div class="sv-addon-sub">' + item.sub + '</div></div>' +
          '</div>' +
          '<div class="sv-addon-right">' + qrow +
            '<div class="sv-addon-price">' + priceTag(item) + '</div>' +
          '</div>' +
        '</div>');
      });
      wrap.innerHTML = rows.join('') +
      '<div class="sv-addon-footer">' +
        '<div class="sv-addon-total-row">' +
          '<span class="sv-addon-total-lbl">Add-ons subtotal</span>' +
          footerTotal() +
        '</div>' +
        '<button class="sv-addon-confirm" id="sv-ao-ok">Confirm selection</button>' +
      '</div>';

      wrap.querySelectorAll(".sv-addon-row").forEach(function(row) {
        row.addEventListener("click", function(e) {
          if (e.target.classList.contains("sv-addon-qbtn")) return; // handled below
          var id = this.dataset.id;
          checked[id] = !checked[id];
          render();
        });
      });
      wrap.querySelectorAll(".sv-addon-qbtn").forEach(function(btn) {
        btn.addEventListener("click", function(e) {
          e.stopPropagation();
          var id = this.dataset.id;
          var dir = parseInt(this.dataset.dir);
          qty[id] = Math.max(1, (qty[id] || 1) + dir);
          render();
        });
      });
      wrap.querySelector("#sv-ao-ok").addEventListener("click", submitAddons);
    }

    function submitAddons() {
      var sel = ITEMS.filter(function(i){ return checked[i.id]; });
      var msg;
      if (sel.length === 0) {
        msg = "No add-ons needed, thanks.";
      } else {
        var lines = sel.map(function(i) {
          if (i.type === "consult") return i.name + " (by consultation)";
          if (i.type === "staff") return i.name + " (full event, €35/hr per person — priced in quote)";
          if (i.type === "hr") return i.name + " (" + qty[i.id] + "h): €" + lineTotal(i);
          if (i.type === "pax") return i.name + " (" + qty[i.id] + " people): €" + lineTotal(i);
          return i.name + ": €" + i.price;
        });
        var nonStaffTotal = ITEMS.reduce(function(s,i){
          return (checked[i.id] && i.type !== "staff") ? s + lineTotal(i) : s;
        }, 0);
        var hasStaff = !!checked["staff"];
        var subtotalStr = hasStaff
          ? (nonStaffTotal > 0 ? "€" + nonStaffTotal + " + staff (priced in quote)" : "staff (priced in quote)")
          : "€" + grandTotal();
        // Append canonical Airtable values for deterministic backend sync
        var atValues = sel.map(function(i){ return i.at; }).join(",");
        msg = "Add-ons: " + lines.join(", ") + ". Subtotal: " + subtotalStr + " [at:" + atValues + "]";
      }
      _pickerConfirm = null;
      wrap.remove();
      sendMessage(msg);
    }

    render();
    msgs.appendChild(wrap);
    _pickerConfirm = submitAddons;
    scrollToContext(msgs, wrap);
  }

  // ── T&C checkbox widget ───────────────────────────────────────────────────
  function isAskingTandC(text) {
    const t = text.toLowerCase();
    return t.includes("selectionsauvage.nl/terms") ||
           (t.includes("terms of use") && (t.includes("confirm") || t.includes("accept") || t.includes("reply")));
  }

  function showTandCWidget() {
    if (_shownWidgets.has("tandc")) return;
    _shownWidgets.add("tandc");
    var msgs = document.getElementById("sv-messages");
    var wrap = document.createElement("div");
    wrap.className = "sv-tandc-wrap";
    var accepted = false;
    var checkoutUrl = _pendingCheckoutUrl;

    var payHtml = checkoutUrl
      ? '<hr class="sv-pay-divider">' +
        '<button class="sv-pay-btn" id="sv-pay-btn" disabled>' +
          '<span>💳</span><span>Pay deposit</span>' +
        '</button>'
      : '<button class="sv-tandc-btn" id="sv-tc-ok" disabled>Confirm &amp; continue</button>';

    wrap.innerHTML =
      '<div class="sv-tandc-label" id="sv-tc-row">' +
        '<div class="sv-tandc-box" id="sv-tc-box"></div>' +
        '<span>I have read and accept the <a class="sv-tandc-link" href="https://sauvage.amsterdam/terms" target="_blank">Terms of Use</a></span>' +
      '</div>' +
      payHtml;

    msgs.appendChild(wrap);

    var box = wrap.querySelector("#sv-tc-box");
    var confirmBtn = wrap.querySelector("#sv-tc-ok");
    var payBtn     = wrap.querySelector("#sv-pay-btn");

    wrap.querySelector("#sv-tc-row").addEventListener("click", function(e) {
      if (e.target.tagName === "A") return;
      accepted = !accepted;
      box.classList.toggle("checked", accepted);
      box.textContent = accepted ? "\u2713" : "";
      if (confirmBtn) confirmBtn.disabled = !accepted;
      if (payBtn)     payBtn.disabled     = !accepted;
    });

    if (confirmBtn) {
      confirmBtn.addEventListener("click", function() {
        if (!accepted) return;
        _pickerConfirm = null;
        wrap.remove();
        sendMessage("\u2705 I have read and accepted the Terms of Use.");
      });
    }

    if (payBtn) {
      payBtn.addEventListener("click", function() {
        if (!accepted) return;
        _pickerConfirm = null;
        wrap.remove();
        sendMessage("\u2705 I have read and accepted the Terms of Use.");
        window.open(checkoutUrl, "_blank");
      });
    }

    _pickerConfirm = function() {
      if (!accepted) return;
      if (payBtn)     payBtn.click();
      else if (confirmBtn) confirmBtn.click();
    };
    scrollToContext(msgs, wrap);
  }

  function showStandalonePayButton(checkoutUrl) {
    if (!checkoutUrl) return;
    var msgs = document.getElementById("sv-messages");
    var wrap = document.createElement("div");
    wrap.className = "sv-tandc-wrap";
    wrap.innerHTML =
      '<button class="sv-pay-btn" id="sv-pay-standalone">' +
        '<span>💳</span><span>Pay deposit</span>' +
      '</button>';
    msgs.appendChild(wrap);
    wrap.querySelector("#sv-pay-standalone").addEventListener("click", function() {
      window.open(checkoutUrl, "_blank");
    });
    scrollToContext(msgs, wrap);
  }

  function isAskingDateTime(text) {
    const t = text.toLowerCase();
    // Only show the calendar when the bot explicitly uses the trigger phrase.
    // The system prompt instructs the bot to say "select your dates" when asking for dates.
    // This prevents the calendar firing on time-only follow-ups or confirmations.
    if (t.includes("arrive") || t.includes("arrival") || t.includes("setup")) return false;
    return t.includes("select your dates") || t.includes("select a date");
  }

  function showDateTimePicker() {
    var msgs = document.getElementById("sv-messages");
    var wrap = document.createElement("div");
    wrap.className = "sv-dt-picker";

    var MONTHS = ["January","February","March","April","May","June",
                  "July","August","September","October","November","December"];
    var DOWS   = ["Mo","Tu","We","Th","Fr","Sa","Su"];
    var DAY_MS = 86400000;

    var selected = [];        // array of timestamps (midnight)
    var customPerDay = false; // toggle: per-day vs same-for-all
    var perDayTimes  = {};    // {ts: {startMins, endMins}}
    var today = new Date(); today.setHours(0,0,0,0);
    var viewYear  = today.getFullYear();
    var viewMonth = today.getMonth();
    var sharedStart = 16 * 60;
    var sharedEnd   = 20 * 60;

    function fmt(m) {
      var h = Math.floor(m/60)%24, mn = m%60;
      return String(h).padStart(2,"0")+":"+String(mn).padStart(2,"0");
    }
    function durStr(s, e) {
      var d = e - s; if (d <= 0) d += 1440;
      var h = Math.floor(d/60), m = d%60;
      return m ? h+"h "+m+"m" : h+"h";
    }
    function getPDT(t) {
      if (!perDayTimes[t]) perDayTimes[t] = {startMins: sharedStart, endMins: sharedEnd};
      return perDayTimes[t];
    }
    function isSel(t) { return selected.indexOf(t) !== -1; }
    function toggle(t) {
      var i = selected.indexOf(t);
      if (i === -1) { selected.push(t); getPDT(t); }
      else { selected.splice(i,1); delete perDayTimes[t]; }
    }
    function rangeWrapClass(t) {
      if (!isSel(t)) return "";
      var prev = isSel(t - DAY_MS), next = isSel(t + DAY_MS);
      if (prev && next) return " sv-range-mid";
      if (prev)         return " sv-range-end";
      if (next)         return " sv-range-start";
      return "";
    }
    function confirmLabel() {
      if (!selected.length) return "Select date(s) to continue";
      var sorted = selected.slice().sort(function(a,b){return a-b;}).map(function(t){return new Date(t);});
      var ds;
      if (sorted.length === 1) {
        ds = sorted[0].toLocaleDateString("en-GB",{weekday:"short",day:"numeric",month:"short"});
      } else if (sorted.length <= 3) {
        ds = sorted.map(function(d){
          return d.toLocaleDateString("en-GB",{day:"numeric",month:"short"});
        }).join(", ");
      } else {
        ds = sorted.length + " dates";
      }
      if (customPerDay && selected.length > 1) {
        return "Confirm \u2014 " + ds + " (custom times)";
      }
      return "Confirm \u2014 " + ds + " \u00B7 " + fmt(sharedStart) + "\u2013" + fmt(sharedEnd);
    }

    function renderTimeSection() {
      var hasDates = selected.length > 0;
      var multiDates = selected.length >= 2;

      // Toggle pill (only shown when 2+ dates selected)
      var toggleHtml = multiDates
        ? '<div class="sv-time-toggle">' +
            '<button class="sv-tt-opt' + (!customPerDay ? ' sv-tt-active' : '') + '" id="sv-tt-all">Same for all</button>' +
            '<button class="sv-tt-opt' + (customPerDay  ? ' sv-tt-active' : '') + '" id="sv-tt-custom">Per day</button>' +
          '</div>'
        : '';

      var timesHtml = '';
      if (!customPerDay || !multiDates) {
        // Shared time controls
        timesHtml =
          '<div class="sv-time-row">' +
            '<span class="sv-time-lbl">Start</span>' +
            '<div class="sv-stepper">' +
              '<button class="sv-step-btn" id="sv-sm">&#x2212;</button>' +
              '<div class="sv-step-val" id="sv-sv">' + fmt(sharedStart) + '</div>' +
              '<button class="sv-step-btn" id="sv-sp">+</button>' +
            '</div>' +
          '</div>' +
          '<div class="sv-time-row">' +
            '<span class="sv-time-lbl">End</span>' +
            '<div class="sv-stepper">' +
              '<button class="sv-step-btn" id="sv-em">&#x2212;</button>' +
              '<div class="sv-step-val" id="sv-ev">' + fmt(sharedEnd) + '</div>' +
              '<button class="sv-step-btn" id="sv-ep">+</button>' +
            '</div>' +
            '<span class="sv-duration" id="sv-dur">' + durStr(sharedStart, sharedEnd) + '</span>' +
          '</div>';
      } else {
        // Per-day controls — one row per selected date
        var sortedTs = selected.slice().sort(function(a,b){return a-b;});
        timesHtml = sortedTs.map(function(t) {
          var pdt = getPDT(t);
          var d   = new Date(t);
          var lbl = d.toLocaleDateString("en-GB",{weekday:"short",day:"numeric",month:"short"});
          return '<div class="sv-time-row">' +
            '<span class="sv-pd-lbl">' + lbl + '</span>' +
            '<div class="sv-stepper">' +
              '<button class="sv-step-btn sv-pd-btn" data-t="' + t + '" data-field="start" data-dir="-1">&#x2212;</button>' +
              '<div class="sv-step-val sv-pd-sv" data-t="' + t + '" data-field="start">' + fmt(pdt.startMins) + '</div>' +
              '<button class="sv-step-btn sv-pd-btn" data-t="' + t + '" data-field="start" data-dir="1">+</button>' +
            '</div>' +
            '<span style="font-size:10px;color:#ccc;padding:0 3px;">–</span>' +
            '<div class="sv-stepper">' +
              '<button class="sv-step-btn sv-pd-btn" data-t="' + t + '" data-field="end" data-dir="-1">&#x2212;</button>' +
              '<div class="sv-step-val sv-pd-sv" data-t="' + t + '" data-field="end">' + fmt(pdt.endMins) + '</div>' +
              '<button class="sv-step-btn sv-pd-btn" data-t="' + t + '" data-field="end" data-dir="1">+</button>' +
            '</div>' +
            '<span class="sv-duration">' + durStr(pdt.startMins, pdt.endMins) + '</span>' +
          '</div>';
        }).join('');
      }

      return '<div class="sv-time-section">' +
        '<div class="sv-time-header">' +
          '<div class="sv-time-section-label">Time</div>' +
          toggleHtml +
        '</div>' +
        timesHtml +
      '</div>';
    }

    function render() {
      var firstDow    = (new Date(viewYear, viewMonth, 1).getDay() + 6) % 7;
      var daysInMonth = new Date(viewYear, viewMonth+1, 0).getDate();
      var cells = "";
      for (var i=0; i<firstDow; i++) cells += '<div class="sv-cal-day-wrap"></div>';
      for (var d=1; d<=daysInMonth; d++) {
        var dt     = new Date(viewYear, viewMonth, d);
        var t      = dt.getTime();
        var isPast = dt < today;
        var isTod  = t === today.getTime();
        var selCls  = isSel(t) ? " sv-cal-selected" : "";
        var todCls  = isTod    ? " sv-cal-today"    : "";
        var wrapCls = "sv-cal-day-wrap" + rangeWrapClass(t);
        cells +=
          '<div class="' + wrapCls + '">' +
            '<button class="sv-cal-day' + selCls + todCls + '" data-t="' + t + '"' +
              (isPast ? ' disabled' : '') + '>' + d + '</button>' +
          '</div>';
      }
      var countTxt = selected.length
        ? selected.length + (selected.length === 1 ? " date selected" : " dates selected")
        : "Tap to select one or more dates";

      wrap.innerHTML =
        '<div class="sv-cal-header">' +
          '<button class="sv-cal-nav" id="sv-prev">\u2039</button>' +
          '<div class="sv-cal-title">' + MONTHS[viewMonth] + " " + viewYear + '</div>' +
          '<button class="sv-cal-nav" id="sv-next">\u203a</button>' +
        '</div>' +
        '<div class="sv-cal-grid">' +
          DOWS.map(function(d){ return '<div class="sv-cal-dow">'+d+'</div>'; }).join("") +
          cells +
        '</div>' +
        '<div class="sv-sel-bar">' +
          '<span class="sv-sel-count">' + countTxt + '</span>' +
          (selected.length ? '<button class="sv-sel-clear" id="sv-clear">Clear</button>' : '') +
        '</div>' +
        renderTimeSection() +
        '<button class="sv-dt-confirm" id="sv-dt-ok"' + (selected.length ? '' : ' disabled') + '>' +
          confirmLabel() +
        '</button>';
      bind();
    }

    function bind() {
      wrap.querySelector("#sv-prev").onclick = function(){ viewMonth--; if(viewMonth<0){viewMonth=11;viewYear--;} render(); };
      wrap.querySelector("#sv-next").onclick = function(){ viewMonth++; if(viewMonth>11){viewMonth=0;viewYear++;} render(); };
      wrap.querySelectorAll(".sv-cal-day:not(:disabled)").forEach(function(b){
        b.onclick = function(){ toggle(parseInt(this.dataset.t)); render(); };
      });
      var clr = wrap.querySelector("#sv-clear");
      if (clr) clr.onclick = function(){ selected = []; perDayTimes = {}; _pickerConfirm = null; render(); };

      // Toggle buttons
      var ttAll = wrap.querySelector("#sv-tt-all");
      var ttCustom = wrap.querySelector("#sv-tt-custom");
      if (ttAll)    ttAll.onclick    = function(){ customPerDay = false; render(); };
      if (ttCustom) ttCustom.onclick = function(){ customPerDay = true; render(); };

      // Shared time steppers
      var smBtn = wrap.querySelector("#sv-sm");
      var spBtn = wrap.querySelector("#sv-sp");
      var emBtn = wrap.querySelector("#sv-em");
      var epBtn = wrap.querySelector("#sv-ep");
      if (smBtn) smBtn.onclick = function(){ sharedStart=(sharedStart-30+1440)%1440; render(); };
      if (spBtn) spBtn.onclick = function(){ sharedStart=(sharedStart+30)%1440;       render(); };
      if (emBtn) emBtn.onclick = function(){ sharedEnd=(sharedEnd-30+1440)%1440;      render(); };
      if (epBtn) epBtn.onclick = function(){ sharedEnd=(sharedEnd+30)%1440;            render(); };

      // Per-day steppers
      wrap.querySelectorAll(".sv-pd-btn").forEach(function(b){
        b.onclick = function(){
          var t   = parseInt(this.dataset.t);
          var fld = this.dataset.field;
          var dir = parseInt(this.dataset.dir);
          var pdt = getPDT(t);
          if (fld === "start") pdt.startMins = (pdt.startMins + dir*30 + 1440) % 1440;
          else                 pdt.endMins   = (pdt.endMins   + dir*30 + 1440) % 1440;
          render();
        };
      });

      // Confirm — always attach handler, guard disabled state inside
      var ok = wrap.querySelector("#sv-dt-ok");
      if (ok) {
        var doConfirm = function() {
          if (ok.disabled || !selected.length) return;
          try {
            var sortedTs = selected.slice().sort(function(a,b){return a-b;});
            var msg;
            if (customPerDay && sortedTs.length > 1) {
              msg = sortedTs.map(function(t){
                var pdt = getPDT(t);
                var d   = new Date(t);
                return d.toLocaleDateString("en-GB",{weekday:"short",day:"numeric",month:"short"}) +
                       " " + fmt(pdt.startMins) + "\u2013" + fmt(pdt.endMins);
              }).join("; ");
            } else {
              var dates = sortedTs.map(function(t){ return new Date(t); });
              var dateStr = dates.length === 1
                ? dates[0].toLocaleDateString("en-GB",{weekday:"long",day:"numeric",month:"long"})
                : dates.map(function(d){
                    return d.toLocaleDateString("en-GB",{weekday:"short",day:"numeric",month:"short"});
                  }).join(", ");
              msg = dateStr + ", " + fmt(sharedStart) + " to " + fmt(sharedEnd);
            }
            _pickerConfirm = null;
            wrap.remove();
            sendMessage(msg);
          } catch(e) {
            console.error("Calendar confirm error:", e);
          }
        };
        ok.onclick = doConfirm;
        _pickerConfirm = doConfirm; // also triggered by main Send button
      }
    }

    render();
    msgs.appendChild(wrap);
    scrollToContext(msgs, wrap);
  }

  // ── API calls ─────────────────────────────────────────────────────────────
  async function initSession() {
    _shownWidgets.clear(); // fresh session = fresh widget slate
    try {
      const r = await fetch(`${API}/chat/session`);
      const data = await r.json();
      sessionId = data.session_id;
      
      // Track booking session initiated
      if (window.gtag) {
        gtag('event', 'booking_session_started', {
          'event_category': 'booking',
          'event_label': 'session_created',
          'session_id': sessionId
        });
      }
    } catch (e) {
      sessionId = "local-" + Date.now();
    }
  }

  async function sendMessage(text) {
    const input = document.getElementById("sv-input");
    const btn = document.getElementById("sv-send");
    if (!text) text = input.value.trim();
    // If calendar is open and input is empty, trigger the picker confirm
    if (!text && _pickerConfirm) { _pickerConfirm(); return; }
    if (!text) return;

    // Secret admin code — simulate payment for testing
    if (text.trim() === "sauvage-test-paid") {
      addMessage("Simulating payment confirmation...", "bot");
      stopPaymentPolling(); // stop polling BEFORE sending confirmation so it can't race
      fetch(API + "/chat/test-confirm/" + sessionId, { method: "POST" })
        .then(function(r){ return r.json(); })
        .then(function(){ sendMessage("Payment confirmed \u2705 \u2014 deposit received."); })
        .catch(function(e){ addMessage("Test error: " + e, "bot"); });
      return;
    }

    // Intercept "paid" keywords — start polling locally, do not send to API
    var _pw = ["paid", "betaald", "payment done", "i paid", "just paid", "payment complete"];
    if (_pw.some(function(w){ return text.toLowerCase().trim() === w; })) {
      addMessage(text, "user");
      addMessage("Thanks! Checking your payment...", "bot");
      setTimeout(startPaymentPolling, 500);
      return;
    }

    // Instant local handoff — triggered by button or by user expressing intent
    if (text === "\uD83D\uDE4B Talk to someone" || wantsHuman(text)) {
      addMessage(text, "user");
      addMessage("Of course! Greg from the Sauvage team can help you directly.\n\n\ud83d\udcde +31 634 742 988\n\ud83d\udcac WhatsApp: https://wa.me/31634742988\n\nJust mention what you're looking for and he'll get back to you quickly \ud83d\udc4b", "bot");
      return;
    }

    // In-flight guard — ignore if a request is already in progress
    if (sendMessage._inflight) return;
    sendMessage._inflight = true;

    input.value = "";
    input.style.height = "auto";
    btn.disabled = true;

    addMessage(text, "user");
    showTyping();

    // Dismiss any open interactive widgets before the API round-trip
    var _widgetSelectors = [
      ".sv-dt-picker", ".sv-ctype-wrap", ".sv-contact-wrap",
      ".sv-addons-wrap", ".sv-attr-wrap", ".sv-tandc-wrap",
      ".sv-arrival-wrap", ".sv-radio-wrap"
    ];
    _widgetSelectors.forEach(function(sel) {
      document.querySelectorAll(sel).forEach(function(el) { el.remove(); });
    });
    _pickerConfirm = null;

    // 45-second timeout — prevents hanging indefinitely if server is slow
    var _controller = new AbortController();
    var _timeout = setTimeout(function() { _controller.abort(); }, 45000);

    try {
      const r = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text }),
        signal: _controller.signal,
      });
      clearTimeout(_timeout);
      const data = await r.json();
      hideTyping();

      if (data.error) {
        addMessage("Our booking assistant is briefly unavailable. Reach Greg directly:\n\n\ud83d\udcde +31 634 742 988\n\ud83d\udcac WhatsApp: https://wa.me/31634742988", "bot");
        showQuickReplies(["\uD83D\uDE4B Talk to someone"]);
      } else {
        const botMsg = data.response;
        sessionId = data.session_id;
        const botDiv = addMessage(botMsg, "bot");
        updateProgress(detectStage(botMsg));

        if (isQuoteMessage(botMsg)) {
          setTimeout(function() { addPdfExportButton(botDiv.innerHTML); }, 200);
        }
        // Store checkout URL for the pay button widget (T&C widget or standalone)
        if (data.checkout_url) {
          _pendingCheckoutUrl = data.checkout_url;
          setTimeout(startPaymentPolling, 1000);
        } else if (hasPaymentLink(botMsg)) {
          setTimeout(startPaymentPolling, 1000);
        }
        var bl = botMsg.toLowerCase();
        // Only stop polling on unambiguous payment-received signals,
        // NOT on T&C confirmation or quote approval (those precede actual payment).
        if (bl.includes("deposit received") || bl.includes("payment received") ||
            (bl.includes("booking is confirmed") && bl.includes("deposit"))) {
          stopPaymentPolling();
        }
        // Widget routing — backend signal takes priority, text matching as fallback.
        // _shownWidgets ensures each widget type appears at most once per session.
        var _widgetMap = {
          "datetime":      function(){ showDateTimePicker(); },
          "contact":       function(){ showContactWidget(); },
          "customer_type": function(){ showCustomerTypeToggle(); },
          "addons":        function(){ showAddonsWidget(data.widget_data || {}); },
          "attribution":   function(){ showAttributionWidget(); },
          "tandc":         function(){ showTandCWidget(); },
        };
        var _nextWidget = data.widget || null;
        if (!_nextWidget) {
          if      (isAskingDateTime(botMsg))                                         _nextWidget = "datetime";
          else if (!_shownWidgets.has("addons") && isAskingAddons(botMsg))           _nextWidget = "addons";
          else if (!_shownWidgets.has("contact")       && isAskingContact(botMsg))       _nextWidget = "contact";
          else if (!_shownWidgets.has("customer_type") && isAskingCustomerType(botMsg))  _nextWidget = "customer_type";
          else if (!_shownWidgets.has("attribution")   && isAskingAttribution(botMsg))   _nextWidget = "attribution";
          else if (!_shownWidgets.has("tandc")         && isAskingTandC(botMsg))         _nextWidget = "tandc";
        }
        if (_nextWidget && _widgetMap[_nextWidget]) {
          setTimeout(_widgetMap[_nextWidget], 300);
        } else if (!_nextWidget && data.checkout_url && _shownWidgets.has("tandc")) {
          // T&C already accepted in this session — show standalone pay button
          setTimeout(function(){ showStandalonePayButton(data.checkout_url); }, 300);
        }
      }
    } catch (e) {
      clearTimeout(_timeout);
      hideTyping();
      if (e.name === "AbortError") {
        addMessage("The request timed out — please try again, or reach Greg directly:\n\n\ud83d\udcde +31 634 742 988\n\ud83d\udcac https://wa.me/31634742988", "bot");
      } else {
        addMessage("Connection error — please try again, or reach Greg directly:\n\n\ud83d\udcde +31 634 742 988\n\ud83d\udcac https://wa.me/31634742988", "bot");
      }
    } finally {
      sendMessage._inflight = false;
      btn.disabled = false;
      input.focus();
    }
  }

  // ── Events ────────────────────────────────────────────────────────────────
  function bindEvents() {
    document.getElementById("sv-bubble").addEventListener("click", togglePanel);
    document.getElementById("sv-send").addEventListener("click", () => sendMessage());

    const input = document.getElementById("sv-input");
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    input.addEventListener("input", function () {
      if (this.value.length > 1000) this.value = this.value.slice(0, 1000);
      this.style.height = "auto";
      this.style.height = Math.min(this.scrollHeight, 100) + "px";
    });
  }

  async function togglePanel() {
    open = !open;
    const panel = document.getElementById("sv-panel");
    const bubble = document.getElementById("sv-bubble");
    panel.classList.toggle("sv-open", open);
    bubble.textContent = open ? "✕" : "💬";

    if (open && !sessionId) {
      await initSession();
      // Display greeting locally — session is pre-seeded on the server
      addMessage("Hey! Welcome to Sauvage 👋\n\nI'm the booking assistant for Sauvage Event Space — Potgieterstraat 47H, Amsterdam.\n\nI can check availability, build your quote, and lock in your booking with a deposit — all right here, no emails needed.\n\nWhat kind of event are you planning?", "bot");
      setTimeout(showEventTypeWidget, 400);
    }
  }

  // ── Nav button ────────────────────────────────────────────────────────────
  function injectNavButton() {
    const navCss = `
      .sv-nav-btn {
        background: #1a1a1a; color: #fff !important; border: none;
        padding: 5px 14px; border-radius: 4px; font-size: 12px;
        font-weight: 600; cursor: pointer; letter-spacing: 0.08em;
        text-decoration: none !important; white-space: nowrap;
        font-family: inherit; transition: background 0.2s;
        display: inline-flex; align-items: center;
        line-height: 1; vertical-align: middle;
        text-transform: uppercase; margin: 0;
      }
      .sv-nav-btn:hover { background: #333 !important; color: #fff !important; }
    `;
    const s = document.createElement("style");
    s.textContent = navCss;
    document.head.appendChild(s);

    const btn = document.createElement("button");
    btn.className = "sv-nav-btn";
    btn.textContent = "Book an Event";
    btn.addEventListener("click", openPanel);

    // 1. Try to append to the nav list (after WINES etc.) — preferred position
    const navListSelectors = [
      "header .header__inline-menu ul",
      "header .header__inline-menu .list-menu",
      "header nav ul",
      ".header__inline-menu ul",
    ];

    let inserted = false;

    for (const sel of navListSelectors) {
      const ul = document.querySelector(sel);
      if (!ul) continue;
      const li = document.createElement("li");
      li.style.cssText = "list-style:none;display:inline-flex;align-items:center;align-self:center;margin:0;";
      li.appendChild(btn);
      ul.appendChild(li);
      inserted = true;
      break;
    }

    // 2. Fall back: insert before the cart icon
    if (!inserted) {
      const cartSelectors = [
        "header .header__icon--cart",
        "header cart-notification-button",
        "header [data-cart-icon-bubble]",
        "header a[href='/cart']",
        "header button[aria-label*='art' i]",
        ".header__icon--cart",
      ];
      for (const sel of cartSelectors) {
        const cartEl = document.querySelector(sel);
        if (!cartEl) continue;
        const iconsWrap = cartEl.closest(
          ".header__icons, .site-header__icons, .header__right, .site-header__right"
        );
        if (iconsWrap) {
          let anchor = cartEl;
          while (anchor.parentNode && anchor.parentNode !== iconsWrap) {
            anchor = anchor.parentNode;
          }
          if (anchor.parentNode === iconsWrap) {
            iconsWrap.insertBefore(btn, anchor);
            inserted = true;
            break;
          }
        }
        if (!inserted && cartEl.parentNode) {
          cartEl.parentNode.insertBefore(btn, cartEl);
          inserted = true;
          break;
        }
      }
    }

    // 3. Last resort: fixed position — never append to header broadly
    if (!inserted) {
      btn.style.cssText = "position:fixed;top:14px;right:100px;z-index:9997;";
      document.body.appendChild(btn);
    }
  }

  // ── CTA button on event pages ─────────────────────────────────────────────
  function injectEventCTA() {
    // Only inject on event space pages
    const path = window.location.pathname.toLowerCase();
    const isEventPage = path.includes("event") || path.includes("book") || path === "/";

    if (!isEventPage) return;

    const ctaCss = `
      .sv-cta-wrap { text-align: center; margin: 28px 0 8px; }
      .sv-cta-btn {
        background: #1a1a1a; color: #fff; border: none;
        padding: 15px 36px; border-radius: 8px; font-size: 16px;
        font-weight: 600; cursor: pointer; letter-spacing: 0.04em;
        font-family: inherit; transition: background 0.2s;
        display: inline-flex; align-items: center; gap: 8px;
      }
      .sv-cta-btn:hover { background: #333; }
    `;
    const s = document.createElement("style");
    s.textContent = ctaCss;
    document.head.appendChild(s);

    const wrap = document.createElement("div");
    wrap.className = "sv-cta-wrap";
    wrap.innerHTML = `<button class="sv-cta-btn">📅 Book an Event</button>`;
    wrap.querySelector("button").addEventListener("click", openPanel);

    // Insert after first h1 or first paragraph on the page
    const target = document.querySelector("h1") || document.querySelector(".page-width p");
    if (target && target.parentNode) {
      target.parentNode.insertBefore(wrap, target.nextSibling);
    }
  }

  // Show calendar widget when bot asks for dates
  function showCalendarPicker() {
    if (typeof window.flatpickr === 'undefined') {
      console.log('Flatpickr not loaded yet');
      return;
    }
    
    var input = document.getElementById('sv-input');
    if (!input) return;
    
    // Initialize flatpickr on the input field
    flatpickr(input, {
      mode: 'range',
      minDate: 'today',
      maxDate: new Date(new Date().setDate(new Date().getDate() + 365)),
      dateFormat: 'M d, Y',
      monthSelectorType: 'dropdown',
      defaultDate: new Date(),
      onChange: function(selectedDates) {
        if (selectedDates.length === 2) {
          var startDate = selectedDates[0].toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
          var endDate = selectedDates[1].toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
          input.value = startDate + ' to ' + endDate;
        } else if (selectedDates.length === 1) {
          input.value = selectedDates[0].toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }
      }
    });
    
    input.focus();
  }

  // Expose global open function for custom buttons
  function openPanel() {
    // Track chatbot open in Google Analytics
    if (window.gtag) {
      gtag('event', 'chatbot_opened', {
        'event_category': 'booking',
        'event_label': 'chatbot_engagement'
      });
    }
    if (!open) togglePanel();
  }
  window.SauvageChat = { open: openPanel, showCalendar: showCalendarPicker };

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    injectStyles();
    buildWidget();
    bindEvents();
    if (!window._svSkipNavInject) injectNavButton();
    // injectEventCTA(); // disabled — CTA button removed per user request
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
