var STORAGE_KEY = 'pp_edge_games';
var ACTIVE_KEY = 'pp_edge_active';
var SELECTED_KEY = 'pp_edge_selected';

function loadGames() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch (e) { return {}; }
}
function saveGames(games) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(games));
}

function renderTabs(games, activeKey) {
    var bar = document.getElementById('tabs-bar');
    var keys = Object.keys(games);
    if (keys.length === 0) { bar.innerHTML = ''; return; }
    var html = '';
    keys.forEach(function(key) {
        var g = games[key];
        var activeClass = (key === activeKey) ? ' active' : '';
        html += '<div class="tab' + activeClass + '" onclick="switchGame(\'' + key + '\')">'
            + g.label
            + ' <span class="tab-close" onclick="event.stopPropagation(); deleteGame(\'' + key + '\')">&times;</span>'
            + '</div>';
    });
    bar.innerHTML = html;
}

function switchGame(key) {
    localStorage.setItem(ACTIVE_KEY, key);
    var games = loadGames();
    renderTabs(games, key);
    if (games[key]) renderColumns(games[key]);
}

function escapeAttr(str) {
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function browseGames() {
    var sport = document.getElementById('sport-select').value;
    var date = document.getElementById('date-input').value;
    var area = document.getElementById('game-browser');

    if (!sport) {
        area.innerHTML = '';
        return;
    }

    area.innerHTML = '<div class="game-list-msg">Loading upcoming games...</div>';

    fetch('/games?sport=' + encodeURIComponent(sport) + '&date=' + encodeURIComponent(date))
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (data.error) {
                area.innerHTML = '<div class="game-list-msg">' + data.error + '</div>';
                return;
            }
            var games = data.games || [];
            if (games.length === 0) {
                area.innerHTML = '<div class="game-list-msg">No upcoming games found for this sport in the next 3 days.</div>';
                return;
            }
            var html = '<div class="game-list">';
            games.forEach(function(g) {
                var timeStr = '';
                if (g.commence_time) {
                    try { timeStr = new Date(g.commence_time).toLocaleString(); }
                    catch (e) { timeStr = g.commence_time; }
                }
                html += '<div class="game-item" data-id="' + escapeAttr(g.id) + '" data-away="' + escapeAttr(g.away_team) + '" data-home="' + escapeAttr(g.home_team) + '" onclick="pickGame(this.dataset.id, this.dataset.away, this.dataset.home)">'
                    + g.away_team + ' @ ' + g.home_team
                    + (timeStr ? '<span class="game-time">' + timeStr + '</span>' : '')
                    + '</div>';
            });
            html += '</div>';
            area.innerHTML = html;
        })
        .catch(function(err) {
            area.innerHTML = '<div class="game-list-msg">Could not load games: ' + err + '</div>';
        });
}

function pickGame(eventId, teamA, teamB) {
    document.getElementById('event-id-input').value = eventId;
    document.getElementById('team-a-input').value = teamA;
    document.getElementById('team-b-input').value = teamB;
    document.getElementById('scan-form').submit();
}

function clearAllGames() {
    if (!confirm('Clear all saved games and any in-progress entry selections? This cannot be undone.')) {
        return;
    }
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(ACTIVE_KEY);
    localStorage.removeItem(SELECTED_KEY);
    selectedLegs = {};
    renderTabs({}, null);
    document.getElementById('results-area').innerHTML = '';
    renderEntryBuilder();
}

function deleteGame(key) {
    var games = loadGames();
    delete games[key];
    saveGames(games);
    Object.keys(selectedLegs).forEach(function(legId) {
        if (legId.indexOf(key + '::') === 0) delete selectedLegs[legId];
    });
    saveSelected();
    var remaining = Object.keys(games);
    var newActive = remaining.length ? remaining[0] : null;
    if (newActive) localStorage.setItem(ACTIVE_KEY, newActive);
    else localStorage.removeItem(ACTIVE_KEY);
    renderTabs(games, newActive);
    if (newActive) renderColumns(games[newActive]);
    else document.getElementById('results-area').innerHTML = '';
    renderEntryBuilder();
}

function badgesForRow(r, rowIdx) {
    var b = '';
    if (r.estimate_type === 'THRESHOLD_LADDER') {
        b += '<span class="badge badge-est">LADDER EST -- single-book, no de-vig</span>';
    } else if (r.estimated) {
        b += '<span class="badge badge-est">EST +' + r.gap + 'pt</span>';
    }
    if (r.deviation !== null && r.deviation !== undefined) {
        var label = r.assumed_multiplier ? ('~' + r.assumed_multiplier + 'x ASSUMED') : 'MULTIPLIER UNKNOWN';
        b += '<span class="badge badge-calib">' + label
            + ' <a href="javascript:void(0)" class="badge-fix" onclick="event.stopPropagation(); event.preventDefault(); correctMultiplier(' + rowIdx + ')">fix</a></span>';
    }
    if (r.single_book) b += '<span class="badge badge-single">SINGLE BOOK</span>';
    if (r.type_conflict) b += '<span class="badge badge-conflict">VERIFY TYPE IN APP</span>';
    return b;
}

function correctMultiplier(rowIdx) {
    if (!currentGameData) return;
    var r = currentGameData.rows[rowIdx];
    if (!r || r.deviation === null || r.deviation === undefined) return;

    var input = prompt(
        'Real total multiplier for a 2-pick entry made of this leg + one standard leg\n'
        + '(same as reading it straight off the PrizePicks picker):',
        r.assumed_multiplier || ''
    );
    if (input === null) return;
    var mult = parseFloat(input);
    if (!mult || mult <= 1.0) {
        alert('Enter a valid multiplier greater than 1, e.g. 2.4');
        return;
    }

    fetch('/calibrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            market: r.market, dfs_type: r.dfs_type, deviation: r.deviation,
            multiplier: mult, consensus_pct: r.consensus_pct
        })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (!data.success) {
            alert(data.message || 'Could not save calibration.');
            return;
        }
        r.assumed_multiplier = data.assumed_multiplier;
        if (data.bar !== undefined) r.bar = data.bar;
        if (data.margin !== undefined) r.margin = data.margin;
        if (data.tier !== undefined) r.tier = data.tier;
        renderFilteredColumns();
    })
    .catch(function(err) {
        alert('Request failed: ' + err);
    });
}

function legRowHtml(r, gameKey, gameLabel, rowIdx) {
    var hasData = r.consensus_pct !== null && r.consensus_pct !== undefined;
    var css = !hasData ? 'noData' : (r.tier === 'TIER A' ? 'tierA' : (r.tier === 'TIER B' ? 'tierB' : 'below'));
    var spread = r.single_book ? 'N/A - SINGLE BOOK' : (r.spread_pct != null ? r.spread_pct + 'pts' : 'N/A');
    var shortMarket = r.market.replace('player_', '').replace('batter_', '').replace('pitcher_', '');
    var label = r.player + ' - ' + r.side + ' ' + shortMarket + ' ' + r.point;
    var legId = gameKey + '::' + r.player + '::' + r.market + '::' + r.point;
    var checkedAttr = selectedLegs[legId] ? 'checked' : '';
    var disabledAttr = hasData ? '' : 'disabled';
    var sideBadge = '<span class="badge badge-side-' + r.side.toLowerCase() + '">' + r.side.toUpperCase() + '</span>';
    var matchupLine = r.matchup ? ('<div class="matchup-line">' + r.matchup + '</div>') : '';

    // Full leg data for spreadsheet logging, base64-encoded to avoid any HTML
    // attribute quote-collision risk (bit us twice already with inline JSON).
    var logData = {
        player: r.player, market: r.market, point: r.point, side: r.side,
        dfs_type: r.dfs_type, consensus_pct: r.consensus_pct, bar: r.bar, margin: r.margin,
        tier: r.tier, whole_number: (r.point !== null && r.point % 1 === 0),
        estimate_type: r.estimate_type, book_point: r.book_point,
        over_price: r.over_price, under_price: r.under_price,
        books: r.books, matchup: r.matchup || '', spread_pct: r.spread_pct,
    };
    var logDataB64 = btoa(unescape(encodeURIComponent(JSON.stringify(logData))));

    var metaLine = hasData
        ? ('Line: ' + r.point + ' | Consensus: ' + r.consensus_pct + '% ' + r.side
            + ' (spread ' + spread + ', books: ' + r.books.join(', ') + ')<br>'
            + 'Break-even: ' + r.bar + '% | Edge margin: ' + (r.margin >= 0 ? '+' : '') + r.margin.toFixed(1) + ' pts | <strong>' + r.tier + '</strong>')
        : ('Line: ' + r.point + ' | No consensus book has a safe line to compare against -- can\'t compute a real edge for this one.'
            + (r.assumed_multiplier ? ' Assumed break-even: ' + r.bar + '%.' : ''));

    return '<div class="leg-row ' + css + '">'
        + '<label>'
        + '<input type="checkbox" class="leg-check" data-legid="' + legId + '" data-label="' + label
        + '" data-consensus="' + r.consensus_pct + '" data-gamelabel="' + gameLabel + '" data-logb64="' + logDataB64 + '" '
        + checkedAttr + ' ' + disabledAttr + ' onchange="toggleLeg(this)">'
        + '<strong>' + r.player + '</strong> — ' + shortMarket + sideBadge + badgesForRow(r, rowIdx)
        + matchupLine
        + '<div class="meta">' + metaLine + '</div></label></div>';
}

// ---- Search + type filtering ----
var currentGameData = null;
var searchQuery = '';
var typeFilters = { goblin: true, regular: true, demon: true };
var rawViewOpen = false;

function matchesFilters(r) {
    var isGoblin = r.dfs_type === 'goblin';
    var isDemon = r.dfs_type === 'demon';
    var isRegular = !isGoblin && !isDemon;
    var typeOk = (isGoblin && typeFilters.goblin) || (isDemon && typeFilters.demon) || (isRegular && typeFilters.regular);
    if (!typeOk) return false;
    if (searchQuery) {
        var q = searchQuery.toLowerCase();
        var playerMatch = r.player.toLowerCase().indexOf(q) !== -1;
        var marketMatch = r.market.toLowerCase().indexOf(q) !== -1;
        return playerMatch || marketMatch;
    }
    return true;
}

function renderFilterBar() {
    var area = document.getElementById('filter-bar-area');
    var html = '<div class="filter-bar">'
        + '<input type="text" id="player-search" placeholder="Search players or stat type (hits, runs, assists...)" oninput="applySearch()">'
        + '<div class="type-toggles">'
        + '<button type="button" class="type-toggle active" data-type="goblin" onclick="toggleTypeFilter(this)">Goblins</button>'
        + '<button type="button" class="type-toggle active" data-type="regular" onclick="toggleTypeFilter(this)">Regular</button>'
        + '<button type="button" class="type-toggle active" data-type="demon" onclick="toggleTypeFilter(this)">Demons</button>'
        + '<button type="button" class="raw-toggle-btn" onclick="toggleRawView()">Show raw data</button>'
        + '</div></div>'
        + '<div id="raw-data-panel" class="raw-data-panel" style="display:none;"></div>';
    area.innerHTML = html;
}

function toggleRawView() {
    rawViewOpen = !rawViewOpen;
    renderRawPanel();
}

function renderRawPanel() {
    var panel = document.getElementById('raw-data-panel');
    if (!panel) return;
    if (!rawViewOpen) { panel.style.display = 'none'; return; }
    panel.style.display = 'block';

    if (!currentGameData) {
        panel.innerHTML = '<div class="game-list-msg">No game selected.</div>';
        return;
    }
    var raw = currentGameData.rawBooks || [];
    var q = searchQuery.toLowerCase();

    var filteredMarkets = raw.map(function(m) {
        var outcomes = m.outcomes || [];
        if (q) {
            outcomes = outcomes.filter(function(o) {
                var desc = (o.description || '').toLowerCase();
                var key = (m.key || '').toLowerCase();
                return desc.indexOf(q) !== -1 || key.indexOf(q) !== -1;
            });
        }
        return { key: m.key, book: m.book, outcomes: outcomes };
    }).filter(function(m) { return m.outcomes.length > 0; });

    var header = q
        ? ('Raw data across all books matching "' + searchQuery + '" (' + filteredMarkets.length + ' market blocks)')
        : ('Raw data across all books -- all ' + filteredMarkets.length + ' market blocks (type in search to filter)');

    panel.innerHTML = '<div class="meta">' + header + '</div><pre class="raw-json">' + escapeAttr(JSON.stringify(filteredMarkets, null, 2)) + '</pre>';
}

function toggleTypeFilter(btn) {
    var type = btn.dataset.type;
    typeFilters[type] = !typeFilters[type];
    btn.classList.toggle('active', typeFilters[type]);
    renderFilteredColumns();
}

function applySearch() {
    searchQuery = document.getElementById('player-search').value;
    renderFilteredColumns();
    renderRawPanel();
}

function renderColumns(gameData) {
    currentGameData = gameData;
    renderFilteredColumns();
    renderRawPanel();
}

function renderFilteredColumns() {
    var area = document.getElementById('results-area');
    if (!currentGameData) { area.innerHTML = ''; return; }

    var gameData = currentGameData;
    var allRows = gameData.rows;
    var rows = allRows.filter(matchesFilters);
    var gameKey = gameData.gameKey;
    var gameLabel = gameData.label;
    var goblins = rows.filter(function(r) { return r.dfs_type === 'goblin'; });
    var demons = rows.filter(function(r) { return r.dfs_type === 'demon'; });
    var regular = rows.filter(function(r) { return r.dfs_type !== 'goblin' && r.dfs_type !== 'demon'; });

    function colHtml(list, emptyMsg) {
        if (list.length === 0) return '<div class="empty-col">' + emptyMsg + '</div>';
        return list.map(function(r) { return legRowHtml(r, gameKey, gameLabel, allRows.indexOf(r)); }).join('');
    }

    var metaText = rows.length === allRows.length
        ? (allRows.length + ' legs scanned | break-even bar: ' + gameData.bar + '%')
        : (rows.length + ' of ' + allRows.length + ' legs shown | break-even bar: ' + gameData.bar + '%');

    var gamesLine = '';
    if (gameData.scannedGames) {
        gamesLine = '<div class="meta">' + gameData.scannedGames.length + ' game(s) included: '
            + gameData.scannedGames.join(', ') + '</div>';
    }

    var html = gameData.skippedNote ? ('<div class="skipped-warning">' + gameData.skippedNote + '</div>') : '';
    html += gamesLine;
    html += '<div class="meta">' + metaText + '</div>';
    html += '<div class="columns-grid">'
        + '<div><div class="column-header goblin">GOBLINS</div>' + colHtml(goblins, 'No Goblin legs found.') + '</div>'
        + '<div><div class="column-header regular">REGULAR</div>' + colHtml(regular, 'No standard legs found.') + '</div>'
        + '<div><div class="column-header demon">DEMONS</div>' + colHtml(demons, 'No Demon legs found.') + '</div>'
        + '</div>';
    area.innerHTML = html;
}

// ---- Cross-game entry selection ----
var selectedLegs = {};

function loadSelected() {
    try { return JSON.parse(localStorage.getItem(SELECTED_KEY)) || {}; }
    catch (e) { return {}; }
}
function saveSelected() {
    localStorage.setItem(SELECTED_KEY, JSON.stringify(selectedLegs));
}

function toggleLeg(checkboxEl) {
    var legId = checkboxEl.dataset.legid;
    if (checkboxEl.checked) {
        var fullData = {};
        try {
            fullData = JSON.parse(decodeURIComponent(escape(atob(checkboxEl.dataset.logb64))));
        } catch (e) { /* fall back to minimal data below if decode fails */ }
        selectedLegs[legId] = {
            label: checkboxEl.dataset.label,
            consensus_pct: parseFloat(checkboxEl.dataset.consensus),
            gameLabel: checkboxEl.dataset.gamelabel,
            fullData: fullData,
        };
    } else {
        delete selectedLegs[legId];
    }
    saveSelected();
    renderEntryBuilder();
}

function removeLeg(legId) {
    delete selectedLegs[legId];
    saveSelected();
    var box = document.querySelector('.leg-check[data-legid="' + legId + '"]');
    if (box) box.checked = false;
    renderEntryBuilder();
}

function renderEntryBuilder() {
    var area = document.getElementById('entry-builder-area');
    var legIds = Object.keys(selectedLegs);

    if (legIds.length === 0) {
        area.innerHTML = '<div class="entry-builder"><strong>Build an entry:</strong> check legs '
            + '(from any game/tab) to combine them here -- selections carry across tabs.</div>';
        return;
    }

    var listHtml = legIds.map(function(legId) {
        var leg = selectedLegs[legId];
        var closeBtn = '<span class="tab-close" data-legid="' + legId + '" onclick="removeLeg(this.dataset.legid)">&times;</span>';
        return '<div class="selected-leg">' + leg.label + ' <span class="meta">(' + leg.gameLabel + ')</span> ' + closeBtn + '</div>';
    }).join('');

    var html = '<div class="entry-builder">'
        + '<strong>Building entry (' + legIds.length + ' leg' + (legIds.length > 1 ? 's' : '') + '):</strong>'
        + '<div style="margin: 0.4rem 0;">' + listHtml + '</div>'
        + 'Real payout multiplier: '
        + '<input type="number" step="0.01" min="1.01" id="entry-mult" placeholder="e.g. 2.3" oninput="calcEntry()">'
        + '<div id="entry-result" class="mult-result"></div>'
        + '<div style="margin-top:0.5rem;">Entry type for log: '
        + '<select id="log-entry-type"><option value="Power">Power</option><option value="Flex">Flex</option></select>'
        + '</div>'
        + '<button type="button" class="log-parlay-btn" onclick="logParlay()">Log this parlay</button>'
        + '<div id="log-parlay-result" class="mult-result"></div>'
        + '</div>';
    area.innerHTML = html;
    calcEntry();
}

function logParlay() {
    var resultEl = document.getElementById('log-parlay-result');
    var multEl = document.getElementById('entry-mult');
    var m = parseFloat(multEl ? multEl.value : NaN);

    if (!m || m <= 1.0) {
        resultEl.innerHTML = '<span style="color:var(--danger)">Enter the real payout multiplier above first.</span>';
        return;
    }

    var legIds = Object.keys(selectedLegs);
    var legsForLog = legIds.map(function(legId) { return selectedLegs[legId].fullData; })
        .filter(function(d) { return d && d.player; });

    if (legsForLog.length === 0) {
        resultEl.innerHTML = '<span style="color:var(--danger)">No loggable leg data found -- try re-selecting the legs.</span>';
        return;
    }

    var typeSelect = document.getElementById('log-entry-type');
    var entryTypeLabel = legIds.length + '-' + (typeSelect ? typeSelect.value : 'Power');
    var today = new Date().toISOString().slice(0, 10);

    resultEl.innerHTML = 'Logging...';
    fetch('/log_parlay', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ legs: legsForLog, multiplier: m, entry_type_label: entryTypeLabel, date: today })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (data.success) {
            resultEl.innerHTML = '<span style="color:var(--success)">' + data.message + '</span>';
        } else {
            resultEl.innerHTML = '<span style="color:var(--danger)">' + data.message + '</span>';
        }
    })
    .catch(function(err) {
        resultEl.innerHTML = '<span style="color:var(--danger)">Request failed: ' + err + '</span>';
    });
}

function calcEntry() {
    var resultEl = document.getElementById('entry-result');
    var multEl = document.getElementById('entry-mult');
    if (!resultEl || !multEl) return;
    var legIds = Object.keys(selectedLegs);
    var m = parseFloat(multEl.value);

    if (legIds.length === 0) {
        resultEl.innerHTML = '';
        return;
    }
    var combinedProb = 1.0;
    legIds.forEach(function(legId) {
        combinedProb *= (selectedLegs[legId].consensus_pct / 100.0);
    });
    var combinedPct = (combinedProb * 100).toFixed(1);

    if (!m || m <= 1.0) {
        resultEl.innerHTML = 'Combined true probability: ' + combinedPct
            + '%. Enter the real multiplier above to see if it clears break-even.';
        return;
    }
    var requiredPct = (100.0 / m);
    var marginPts = (combinedPct - requiredPct);
    var tier = marginPts < 1.5 ? 'BELOW BAR' : (marginPts < 4.0 ? 'TIER B' : 'TIER A');
    var color = tier === 'TIER A' ? 'var(--accent)' : (tier === 'TIER B' ? 'var(--warning)' : 'var(--text-muted)');
    resultEl.innerHTML = 'Combined true probability: ' + combinedPct + '% | Required (1/multiplier): '
        + requiredPct.toFixed(1) + '%<br>'
        + 'Real edge margin: ' + (marginPts >= 0 ? '+' : '') + marginPts.toFixed(1) + ' pts | '
        + '<strong style="color:' + color + '">' + tier + '</strong>';
}

// ---- Page load: merge any new scan into storage, then render from storage ----
(function() {
    var payloadEl = document.getElementById('scan-payload');
    var games = loadGames();
    var activeKey = localStorage.getItem(ACTIVE_KEY);
    selectedLegs = loadSelected();

    if (payloadEl) {
        try {
            var payload = JSON.parse(payloadEl.textContent);
            games[payload.gameKey] = payload;
            saveGames(games);
            activeKey = payload.gameKey;
            localStorage.setItem(ACTIVE_KEY, activeKey);
        } catch (e) { /* no valid new scan, ignore */ }
    }

    if (!activeKey || !games[activeKey]) {
        var keys = Object.keys(games);
        activeKey = keys.length ? keys[0] : null;
    }

    renderTabs(games, activeKey);
    renderFilterBar();
    renderEntryBuilder();
    if (activeKey && games[activeKey]) renderColumns(games[activeKey]);

    var sportSelect = document.getElementById('sport-select');
    if (sportSelect && sportSelect.value) browseGames();
})();
