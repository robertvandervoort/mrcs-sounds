(function () {
  "use strict";

  var library = document.getElementById("library");
  var search = document.getElementById("search");
  var count = document.getElementById("count");
  var sounds = [];

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function formatSize(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
    return Math.round(bytes / 1024) + " KB";
  }

  function formatDuration(sec) {
    var m = Math.floor(sec / 60);
    var s = Math.round(sec - m * 60);
    if (s === 60) { m += 1; s = 0; }
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function matches(sound, query) {
    if (!query) return true;
    var hay = [sound.name, sound.id, sound.category, sound.license, sound.attribution]
      .join(" ").toLowerCase();
    return query.split(/\s+/).every(function (word) { return hay.indexOf(word) !== -1; });
  }

  function card(sound) {
    var item = el("article", "sound");
    item.appendChild(el("h3", "", sound.name));

    var meta = el("div", "meta");
    meta.appendChild(el("span", "", formatDuration(sound.durationSec)));
    meta.appendChild(el("span", "", formatSize(sound.sizeBytes)));
    meta.appendChild(el("span", "", sound.format.toUpperCase() + ", " + sound.sampleRate + " Hz, " +
      (sound.channels === 1 ? "mono" : "stereo")));
    meta.appendChild(el("span", "", "Licence: " + sound.license));
    var link = el("a", "", "Download");
    link.href = sound.path;
    link.setAttribute("download", "");
    meta.appendChild(link);
    item.appendChild(meta);

    var audio = el("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = sound.path;
    item.appendChild(audio);

    if (sound.attribution) item.appendChild(el("p", "attribution", sound.attribution));
    return item;
  }

  function render() {
    var query = search.value.trim().toLowerCase();
    var shown = sounds.filter(function (s) { return matches(s, query); });
    library.textContent = "";
    count.textContent = shown.length + " of " + sounds.length + " sounds";

    if (!shown.length) {
      library.appendChild(el("p", "muted", "No sounds match that search."));
      return;
    }

    var byCategory = {};
    shown.forEach(function (s) { (byCategory[s.category] = byCategory[s.category] || []).push(s); });
    Object.keys(byCategory).sort().forEach(function (category) {
      var section = el("section");
      section.appendChild(el("h2", "", category));
      byCategory[category].forEach(function (s) { section.appendChild(card(s)); });
      library.appendChild(section);
    });
  }

  fetch("index.json", { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (doc) {
      sounds = doc.sounds || [];
      search.addEventListener("input", render);
      render();
    })
    .catch(function (err) {
      library.textContent = "";
      library.appendChild(el("p", "muted", "Could not load index.json: " + err.message));
    });
})();
