var STORAGE_KEY = 'pp_edge_games';
var ACTIVE_KEY = 'pp_edge_active';
var SELECTED_KEY = 'pp_edge_selected';
var BREAKEVEN_EXPANDED_KEY = 'pp_edge_breakeven_expanded';

// Collapsed by default -- static reference data, not worth permanent screen
// space (see idea #3). Remembers your preference across reloads.
function toggleBreakevenChart() {
    var body = document.getElementById('breakeven-chart-body');
    var chevron = document.getElementById('breakeven-chevron');
    if (!body || !chevron) return;
    var expand = body.style.display === 'none';
    body.style.display = expand ? 'block' : 'none';
    chevron.textContent = expand ? '▾' : '▸';
    try { localStorage.setItem(BREAKEVEN_EXPANDED_KEY, expand ? '1' : '0'); } catch (e) { /* ignore */ }
}

function spinnerHtml(text) {
    return '<span class="loading-msg"><span class="spinner"></span>' + text + '</span>';
}

// The scan form is a real page navigation (POST + full reload), not an AJAX
// call, so there's no natural place to show progress -- and some scans take
// several real seconds (PropLine's own response time for a heavy game), during
// which the old page just sits there looking frozen. This fires the instant
// you click, before the browser navigates away, and disables the submit
// buttons so an impatient second click can't fire a duplicate scan.
function handleScanFormSubmit(form) {
    var msgEl = document.getElementById('scan-loading-msg');
    if (msgEl) {
        msgEl.style.display = 'block';
        msgEl.innerHTML = spinnerHtml('Scanning -- this can take several seconds for a game with a lot of books/props posted...');
    }
    var buttons = form.querySelectorAll('button[type="submit"]');
    for (var i = 0; i < buttons.length; i++) buttons[i].disabled = true;
    return true;
}

function loadGames() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch (e) { return {}; }
}
function saveGames(games) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(games));
        return true;
    } catch (e) {
        return false;
    }
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
        area.innerHTML = '<div class="game-list-msg game-list-empty">Pick a sport above to see upcoming games.</div>';
        return;
    }

    area.innerHTML = '<div class="game-list-msg">' + spinnerHtml('Loading upcoming games...') + '</div>';

    fetch('/games?sport=' + encodeURIComponent(sport) + '&date=' + encodeURIComponent(date))
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (data.error) {
                area.innerHTML = '<div class="game-list-msg">' + data.error + '</div>';
                return;
            }
            var games = data.games || [];
            if (games.length === 0) {
                area.innerHTML = '<div class="game-list-msg game-list-empty">No upcoming games found for this sport in the next 3 days.</div>';
                return;
            }

            games.sort(function(a, b) {
                return (a.commence_time || '').localeCompare(b.commence_time || '');
            });

            // Group into day sections so a 3-day window reads as "Fri, Sat,
            // Sun" instead of one flat undifferentiated list.
            var dayOrder = [];
            var dayGames = {};
            games.forEach(function(g) {
                var dayKey = 'Date unknown', timeStr = '';
                if (g.commence_time) {
                    try {
                        var d = new Date(g.commence_time);
                        dayKey = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
                        timeStr = d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
                    } catch (e) { timeStr = g.commence_time; }
                }
                if (!dayGames[dayKey]) { dayGames[dayKey] = []; dayOrder.push(dayKey); }
                dayGames[dayKey].push({ g: g, timeStr: timeStr });
            });

            var html = '<div class="game-list">';
            dayOrder.forEach(function(dayKey) {
                html += '<div class="game-day-header">' + dayKey + '</div>';
                dayGames[dayKey].forEach(function(entry) {
                    var g = entry.g;
                    html += '<div class="game-item" data-id="' + escapeAttr(g.id) + '" data-away="' + escapeAttr(g.away_team) + '" data-home="' + escapeAttr(g.home_team) + '" onclick="pickGame(this.dataset.id, this.dataset.away, this.dataset.home)">'
                        + '<span class="game-teams">' + escapeAttr(g.away_team) + ' <span class="game-at">@</span> ' + escapeAttr(g.home_team) + '</span>'
                        + (entry.timeStr ? '<span class="game-time">' + escapeAttr(entry.timeStr) + '</span>' : '')
                        + '</div>';
                });
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
    var form = document.getElementById('scan-form');
    // form.submit() bypasses the "submit" event entirely (a real browser
    // quirk, same class as .checked not firing "change") -- so the onsubmit
    // handler on the form tag never runs for this path. Call it directly.
    handleScanFormSubmit(form);
    form.submit();
}

function checkResults() {
    var statusEl = document.getElementById('check-results-status');
    if (statusEl) statusEl.innerHTML = spinnerHtml('Checking...');

    fetch('/check_results', { method: 'POST' })
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (statusEl) statusEl.textContent = data.message || (data.success ? 'Done.' : 'Failed.');
        })
        .catch(function(err) {
            if (statusEl) statusEl.textContent = 'Request failed: ' + err;
        });
}

function checkClv() {
    var statusEl = document.getElementById('check-clv-status');
    if (statusEl) statusEl.innerHTML = spinnerHtml('Checking...');

    fetch('/check_clv', { method: 'POST' })
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (statusEl) statusEl.textContent = data.message || (data.success ? 'Done.' : 'Failed.');
        })
        .catch(function(err) {
            if (statusEl) statusEl.textContent = 'Request failed: ' + err;
        });
}

// ---- Calibration report -- see calibration_report.py for why this is
// split into two different checks instead of one blended "hit rate by
// tier" number (tier isn't comparable across leg types since goblin/demon
// bars vary per leg while standard/discount bars are flat).
function viewCalibrationReport() {
    var area = document.getElementById('calibration-report-area');
    area.innerHTML = '<div class="raw-data-panel">' + spinnerHtml('Loading...') + '</div>';

    fetch('/calibration_report')
        .then(function(resp) { return resp.json(); })
        .then(function(resp) {
            if (!resp.success) {
                area.innerHTML = '<div class="raw-data-panel"><div class="game-list-msg">' + resp.message + '</div></div>';
                return;
            }
            var d = resp.data;
            if (!d || d.total_graded === 0) {
                area.innerHTML = '<div class="raw-data-panel"><div class="game-list-msg">' + resp.message + '</div></div>';
                return;
            }

            var html = '<div class="raw-data-panel">';
            html += '<div class="meta">' + d.total_graded + ' graded pick(s) | Brier score: '
                + (d.brier_score != null ? d.brier_score : 'N/A')
                + ' (0 = perfect calibration, 0.25 = no better than a coin flip)</div>';

            html += '<div class="section-label" style="margin-top:0.8rem;">Standard/Discount picks by Tier</div>';
            html += '<div class="meta">Bar is flat for these, so tier ordering is a real, uncounfounded hit-rate check.</div>';
            if (d.fixed_bar_by_tier.length === 0) {
                html += '<div class="game-list-msg">No graded standard/discount picks yet.</div>';
            } else {
                html += '<table><tr><th>Tier</th><th>N</th><th>Hit Rate</th></tr>';
                d.fixed_bar_by_tier.forEach(function(row) {
                    html += '<tr><td>' + row.tier + '</td><td>' + row.n + '</td><td>' + (row.hit_rate * 100).toFixed(1) + '%</td></tr>';
                });
                html += '</table>';
            }

            html += '<div class="section-label" style="margin-top:0.8rem;">Goblin/Demon calibration curve (by predicted probability, not Tier)</div>';
            html += '<div class="meta">Bar varies per leg for these, so Tier isn\'t comparable across them -- '
                + 'checking predicted probability vs. actual hit rate instead. A well-calibrated model has '
                + 'these two columns roughly matching in every row.</div>';
            if (d.variable_bar_calibration.length === 0) {
                html += '<div class="game-list-msg">No graded goblin/demon picks yet.</div>';
            } else {
                html += '<table><tr><th>Predicted range</th><th>N</th><th>Avg Predicted</th><th>Actual Hit Rate</th></tr>';
                d.variable_bar_calibration.forEach(function(row) {
                    html += '<tr><td>' + row.bucket + '</td><td>' + row.n + '</td><td>' + row.avg_predicted
                        + '%</td><td>' + row.actual_hit_rate + '%</td></tr>';
                });
                html += '</table>';
            }
            html += '</div>';
            area.innerHTML = html;
        })
        .catch(function(err) {
            area.innerHTML = '<div class="raw-data-panel"><div class="game-list-msg">Request failed: ' + err + '</div></div>';
        });
}

// Empirical same-game correlation, from your OWN graded results -- not the
// AI's pre-bet opinion (see checkEntryCorrelation). See correlation_report.py
// for why this needs real sample size before the percentages mean anything.
function viewCorrelationReport() {
    var area = document.getElementById('correlation-report-area');
    area.innerHTML = '<div class="raw-data-panel">' + spinnerHtml('Loading...') + '</div>';

    fetch('/correlation_report')
        .then(function(resp) { return resp.json(); })
        .then(function(resp) {
            if (!resp.success) {
                area.innerHTML = '<div class="raw-data-panel"><div class="game-list-msg">' + resp.message + '</div></div>';
                return;
            }
            var d = resp.data;
            if (!d || d.total_legs === 0) {
                area.innerHTML = '<div class="raw-data-panel"><div class="game-list-msg">' + resp.message + '</div></div>';
                return;
            }

            var html = '<div class="raw-data-panel">';
            html += '<div class="meta">' + d.total_legs + ' graded leg(s) overall | your overall hit rate: ' + d.overall_hit_rate + '%</div>';

            if (!d.summary) {
                html += '<div class="game-list-msg" style="margin-top:0.6rem;">No same-game leg pairs yet -- '
                    + 'this needs at least 2 graded legs from the same date + matchup to compare. Keep logging and checking results.</div>';
            } else {
                var s = d.summary;
                html += '<div class="section-label" style="margin-top:0.8rem;">Same-game pairs (' + s.total_pairs + ')</div>';
                html += '<div class="meta">Both hit: ' + s.both_hit_pct + '% | Both missed: ' + s.both_miss_pct
                    + '% | Split: ' + s.split_pct + '%<br>'
                    + 'Rough independence baseline (your overall hit rate squared): ' + s.expected_both_hit_pct_if_independent + '% both-hit. '
                    + 'If your real "both hit" % is well above that, same-game legs may be moving together more than independent math assumes.</div>';
                if (s.total_pairs < 15) {
                    html += '<div class="meta" style="color:var(--warning);">Only ' + s.total_pairs + ' pair(s) so far -- '
                        + 'too few to draw a real conclusion from yet. This becomes more meaningful as it accumulates.</div>';
                }

                html += '<div class="section-label" style="margin-top:0.8rem;">Every same-game pair</div>';
                html += '<table><tr><th>Date</th><th>Matchup</th><th>Leg A</th><th>Leg B</th><th>Outcome</th></tr>';
                d.pairs.forEach(function(p) {
                    html += '<tr><td>' + escapeAttr(p.date) + '</td><td>' + escapeAttr(p.matchup) + '</td><td>'
                        + escapeAttr(p.leg_a) + '</td><td>' + escapeAttr(p.leg_b) + '</td><td>' + p.outcome + '</td></tr>';
                });
                html += '</table>';
            }
            html += '</div>';
            area.innerHTML = html;
        })
        .catch(function(err) {
            area.innerHTML = '<div class="raw-data-panel"><div class="game-list-msg">Request failed: ' + err + '</div></div>';
        });
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

// One prominent chip communicates tier at a glance instead of burying it in
// a sentence of meta text -- the single most important signal on the card
// (S/A picks get a tinted card background too, see the tierS/tierA CSS).
var TIER_CHIP_LABEL = { 'TIER S': 'S', 'TIER A': 'A', 'TIER B': 'B', 'TIER C': 'C', 'BELOW BAR': 'BELOW BAR', 'UNKNOWN': '?', 'NO DATA': '--' };
var TIER_CHIP_CLASS = { 'TIER S': 'chip-S', 'TIER A': 'chip-A', 'TIER B': 'chip-B', 'TIER C': 'chip-C', 'BELOW BAR': 'chip-below', 'UNKNOWN': 'chip-unknown', 'NO DATA': 'chip-nodata' };

function tierChip(tier) {
    var cls = TIER_CHIP_CLASS[tier] || 'chip-below';
    var label = TIER_CHIP_LABEL[tier] || tier;
    return '<span class="tier-chip ' + cls + '">' + label + '</span>';
}

function statChip(label, value) {
    return '<div class="stat"><span class="stat-label">' + label + '</span><span class="stat-value">' + value + '</span></div>';
}

// Badges split into always-visible (changes how you should read the number:
// origin, payout structure, a real data-quality warning) vs. tucked behind a
// per-card "Details" toggle (nice-to-know, but stacking every badge on every
// card made a leg with several caveats wrap across multiple lines).
function primaryBadgesForRow(r, rowIdx) {
    var b = '';
    if (r.manual) b += '<span class="badge badge-calib">MANUAL</span>';
    if (r.dfs_type === 'discount') b += '<span class="badge badge-single">DISCOUNT -- standard payout</span>';
    if (r.type_conflict) b += '<span class="badge badge-conflict">VERIFY TYPE IN APP</span>';
    // Kept visible, not tucked behind Details -- this is the assumed payout
    // multiplier driving the leg's whole grade (or a flag that it's missing),
    // and the "fix" action to correct it, so it shouldn't need an extra click.
    if (r.deviation !== null && r.deviation !== undefined) {
        var label = r.assumed_multiplier ? ('~' + r.assumed_multiplier + 'x ASSUMED') : 'MULTIPLIER UNKNOWN';
        b += '<span class="badge badge-calib">' + label
            + ' <a href="javascript:void(0)" class="badge-fix" onclick="event.stopPropagation(); event.preventDefault(); correctMultiplier(' + rowIdx + ')">fix</a></span>';
    }
    return b;
}

function secondaryBadgesForRow(r) {
    var b = '';
    if (r._boosted) b += '<span class="badge badge-calib">' + profitBoostPct + '% BOOST APPLIED</span>';
    if (r.estimate_type === 'THRESHOLD_LADDER') {
        b += '<span class="badge badge-est">LADDER EST -- single-book, no de-vig</span>';
    } else if (r.estimated) {
        b += '<span class="badge badge-est">EST +' + r.gap + 'pt</span>';
    }
    if (r.single_book) b += '<span class="badge badge-single">SINGLE BOOK</span>';
    return b;
}

function toggleLegDetails(rowIdx) {
    var el = document.getElementById('leg-details-' + rowIdx);
    if (!el) return;
    el.style.display = (el.style.display === 'none') ? 'block' : 'none';
}

function legRowHtml(r, gameKey, gameLabel, rowIdx) {
    var hasData = r.consensus_pct !== null && r.consensus_pct !== undefined;
    var TIER_CSS = { 'TIER S': 'tierS', 'TIER A': 'tierA', 'TIER B': 'tierB', 'TIER C': 'tierC', 'UNKNOWN': 'tierUnknown' };
    var css = !hasData ? 'noData' : (TIER_CSS[r.tier] || 'below');
    var spread = r.single_book ? 'N/A - SINGLE BOOK' : (r.spread_pct != null ? r.spread_pct + 'pts' : 'N/A');
    var shortMarket = shortMarketLabel(r.market);
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
        // sport/event_id (tagged on every row at scan time -- see propline_api.py
        // scan_slate and server.py handle_scan/handle_grade_manual) let a later
        // "check results" pass re-fetch this exact game's box score directly,
        // instead of re-matching team names/dates against the API.
        sport: r.sport || '', event_id: r.eventId || '',
    };
    var logDataB64 = btoa(unescape(encodeURIComponent(JSON.stringify(logData))));

    // Key numbers as compact stat chips instead of a prose sentence -- much
    // faster to scan across dozens of cards than reading "Line: X | Consensus:
    // Y% Z (spread W, books: ...) -- Break-even: A% | Edge margin: +B pts" every
    // single time. Secondary detail (spread/books) stays as small text below.
    var statsHtml, extraLine;
    if (!hasData) {
        statsHtml = '<div class="leg-stats">' + statChip('Line', r.point) + '</div>';
        extraLine = 'No consensus book has a safe line to compare against -- can\'t compute a real edge for this one.'
            + (r.assumed_multiplier ? ' Assumed break-even: ' + r.bar + '%.' : '');
    } else if (r.margin === null || r.margin === undefined) {
        // Goblin/demon leg with no calibration data for this market/deviation yet --
        // true probability is real (shown below), but grading it against a payout
        // we don't actually know would be a fabricated tier, so none is assigned
        // (the "?" chip communicates that -- no need to repeat it in prose here).
        statsHtml = '<div class="leg-stats">'
            + statChip('Line', r.point) + statChip('Consensus', r.consensus_pct + '% ' + r.side)
            + '</div>';
        extraLine = 'Spread: ' + spread + ' | Books: ' + r.books.join(', ')
            + '<br>Payout multiplier unknown for this market/deviation.';
    } else {
        // Tier itself is shown by the chip in the header now, not repeated here.
        statsHtml = '<div class="leg-stats">'
            + statChip('Line', r.point) + statChip('Consensus', r.consensus_pct + '% ' + r.side)
            + statChip('Break-even', r.bar + '%')
            + statChip('Margin', (r.margin >= 0 ? '+' : '') + r.margin.toFixed(1) + ' pts')
            + '</div>';
        extraLine = 'Spread: ' + spread + ' | Books: ' + r.books.join(', ');
    }

    var secondaryHtml = secondaryBadgesForRow(r);
    var detailsHtml = secondaryHtml
        ? ('<button type="button" class="details-toggle" onclick="event.stopPropagation(); toggleLegDetails(' + rowIdx + ')">Details ▾</button>'
            + '<div id="leg-details-' + rowIdx + '" class="leg-details" style="display:none;">' + secondaryHtml + '</div>')
        : '';

    return '<div class="leg-row ' + css + '" onclick="handleLegRowClick(event, this)">'
        + '<div class="leg-content">'
        + '<div class="leg-header">'
        + '<input type="checkbox" class="leg-check" data-legid="' + legId + '" data-label="' + label
        + '" data-consensus="' + r.consensus_pct + '" data-gamelabel="' + gameLabel + '" data-logb64="' + logDataB64 + '" '
        + checkedAttr + ' ' + disabledAttr + ' onchange="toggleLeg(this)">'
        + '<span class="leg-title"><strong>' + r.player + '</strong> — ' + shortMarket + sideBadge + '</span>'
        + tierChip(r.tier)
        + '</div>'
        + primaryBadgesForRow(r, rowIdx)
        + matchupLine
        + statsHtml
        + '<div class="meta">' + extraLine + '</div>'
        + detailsHtml
        + '</div>'
        + '<button type="button" class="browse-btn" style="margin-top:0.4rem;font-size:0.75rem;padding:0.35rem 0.7rem;" '
        + 'onclick="event.stopPropagation(); checkLegContext(' + rowIdx + ')">Check context (AI)</button>'
        + '<div id="context-result-' + rowIdx + '" class="raw-data-panel" style="display:none;margin-top:0.4rem;padding:0.6rem;"></div>'
        + '</div>';
}

// Whole-card click toggles selection -- clicking directly on the checkbox
// (native onchange already handles it), a button, or a link inside the card
// (e.g. "Check context", the calibration "fix" link) is excluded so those
// keep their own single action instead of also flipping selection.
function handleLegRowClick(event, cardEl) {
    if (event.target.closest('input, button, a')) return;
    var checkbox = cardEl.querySelector('.leg-check');
    if (!checkbox || checkbox.disabled) return;
    checkbox.checked = !checkbox.checked;
    toggleLeg(checkbox);
}

// ---- Advisory-only AI research (Gemini + Google Search grounding) --
// never touches consensus_pct/bar/tier, see ai_context.py for why. Purely
// human-readable text the user reads and weighs themselves.
function checkLegContext(rowIdx) {
    var gd = currentGameData;
    if (!gd) return;
    var r = gd.rows[rowIdx];
    if (!r) return;

    var resultEl = document.getElementById('context-result-' + rowIdx);
    if (!resultEl) return;
    resultEl.style.display = 'block';
    resultEl.innerHTML = spinnerHtml('Researching (this calls out to Gemini, may take a few seconds)...');

    fetch('/check_context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            player: r.player, matchup: r.matchup || gd.label, sport: gd.sport,
            market_label: shortMarketLabel(r.market), side: r.side, point: r.point
        })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (!data.success) {
            resultEl.innerHTML = '<div class="game-list-msg" style="color:var(--danger)">' + data.text + '</div>';
            return;
        }
        resultEl.innerHTML = '<pre class="raw-json">' + escapeAttr(data.text) + '</pre>';
    })
    .catch(function(err) {
        resultEl.innerHTML = '<div class="game-list-msg" style="color:var(--danger)">Request failed: ' + err + '</div>';
    });
}

// ---- Search + type filtering ----
var currentGameData = null;
var searchQuery = '';
var typeFilters = { goblin: true, regular: true, demon: true };
var rawViewOpen = false;
var profitBoostPct = 0;

// A payout boost (e.g. PrizePicks' "25% profit boost" promos) scales the
// whole entry's final multiplier, and since a leg's break-even bar is just
// 100/multiplier, scaling the bar by the same factor is exact -- no need to
// know the real multiplier, just the % boost. Applied purely as a display
// transform (never mutates the stored row), so turning the boost off always
// reverts cleanly. Mirrors grade_leg()'s tiers in scoring.py exactly.
var TIER_S_MARGIN = 8.0;
var TIER_A_MARGIN = 5.0;
var TIER_B_MARGIN = 3.0;
var TIER_C_MARGIN = 1.5;

function tierForMargin(margin) {
    if (margin < TIER_C_MARGIN) return 'BELOW BAR';
    if (margin < TIER_B_MARGIN) return 'TIER C';
    if (margin < TIER_A_MARGIN) return 'TIER B';
    if (margin < TIER_S_MARGIN) return 'TIER A';
    return 'TIER S';
}

// P(exactly k of N independent events occur), for k = 0..N, from each
// event's own probability -- NOT assuming they're all equal. Needed because
// a Flex entry pays out at multiple hit-count tiers (not just all-or-
// nothing like Power), so grading it as "P(all hit) >= 1/multiplier" ignores
// real value from the lower tiers entirely. Standard Poisson binomial via DP.
function poissonBinomialDist(probs) {
    var dist = [1];
    probs.forEach(function(p) {
        var next = new Array(dist.length + 1).fill(0);
        for (var k = 0; k < dist.length; k++) {
            next[k] += dist[k] * (1 - p);
            next[k + 1] += dist[k] * p;
        }
        dist = next;
    });
    return dist;
}

// Mirrors the static breakeven-chart's Flex payout table -- sensible
// defaults only. PrizePicks multipliers can vary by lineup/promos (see the
// chart's own footnote), so these are pre-filled but always editable to
// whatever real number the app is actually showing for this entry.
var FLEX_PAYOUT_DEFAULTS = {
    3: { oneMiss: 1, twoMiss: null },
    4: { oneMiss: 1.5, twoMiss: null },
    5: { oneMiss: 2, twoMiss: 0.4 },
    6: { oneMiss: 2, twoMiss: 0.4 },
};

function withBoost(r) {
    if (!profitBoostPct || r.bar == null) return r;
    var factor = 1 + profitBoostPct / 100;
    var boostedBar = Math.round((r.bar / factor) * 10) / 10;
    var copy = Object.assign({}, r, { bar: boostedBar, _boosted: true });
    if (r.consensus_pct != null) {
        var boostedMargin = Math.round((r.consensus_pct - boostedBar) * 10) / 10;
        copy.margin = boostedMargin;
        copy.tier = tierForMargin(boostedMargin);
    }
    return copy;
}

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
        + '<label style="display:flex;align-items:center;gap:0.4rem;font-size:0.85rem;color:var(--text-secondary);white-space:nowrap;margin:0;">'
        + 'Profit boost <input type="number" id="profit-boost-input" min="0" step="1" placeholder="0" value="' + (profitBoostPct || '') + '" '
        + 'style="width:70px;margin:0;padding:0.4rem 0.5rem;" oninput="applyBoost()">%'
        + '</label>'
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

function applyBoost() {
    var val = parseFloat(document.getElementById('profit-boost-input').value);
    profitBoostPct = (val > 0) ? val : 0;
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
    renderManualLegForm();
}

// ---- Manual/discounted picks (e.g. "Taco Tuesday" promos PropLine's feed
// doesn't carry) -- graded against the same real consensus books as any
// scanned leg, just fed a hand-typed player/market/point instead of one
// pulled from PrizePicks' own feed. Needs one specific event's odds to check
// against, so gameEvents lists every game in the current tab (one entry for
// a single-game tab, one per game for a slate tab) and the form asks which
// one the pick belongs to whenever there's more than one to choose from.
// Clean display names for every market key across all four sports, so cards
// show "Hits+Runs+RBIs" instead of the raw "hits_runs_rbis"-style feed key.
var MARKET_LABELS = {
    // Basketball (NBA/WNBA)
    player_points: 'Points',
    player_rebounds: 'Rebounds',
    player_assists: 'Assists',
    player_points_rebounds_assists: 'Points+Rebounds+Assists',
    player_threes: '3-Pointers Made',
    player_blocks: 'Blocks',
    player_steals: 'Steals',
    // MLB
    batter_hits: 'Hits',
    batter_home_runs: 'Home Runs',
    batter_rbis: 'RBIs',
    batter_hits_runs_rbis: 'Hits+Runs+RBIs',
    batter_runs_scored: 'Runs Scored',
    batter_stolen_bases: 'Stolen Bases',
    batter_total_bases: 'Total Bases',
    pitcher_strikeouts: 'Strikeouts',
    pitcher_hits_allowed: 'Hits Allowed',
    pitcher_walks: 'Walks',
    pitcher_outs: 'Outs',
    // NFL
    player_pass_yds: 'Passing Yards',
    player_pass_tds: 'Passing TDs',
    player_pass_completions: 'Completions',
    player_pass_attempts: 'Pass Attempts',
    player_pass_interceptions: 'Interceptions',
    player_rush_yds: 'Rushing Yards',
    player_rush_attempts: 'Rush Attempts',
    player_receptions: 'Receptions',
    player_reception_yds: 'Receiving Yards',
    player_pass_rush_reception_yds: 'Pass+Rush+Rec Yards',
    player_kicking_points: 'Kicking Points',
    player_field_goals: 'Field Goals Made',
    player_anytime_td: 'Anytime TD',
};

function shortMarketLabel(key) {
    if (MARKET_LABELS[key]) return MARKET_LABELS[key];
    // Fallback for any market key not in the table above (e.g. a brand-new
    // market before someone adds it here) -- still readable, just less polished.
    var stripped = key.replace(/^(player_|batter_|pitcher_)/, '');
    return stripped.split('_').map(function(word) {
        return word.charAt(0).toUpperCase() + word.slice(1);
    }).join(' ');
}

function renderManualLegForm() {
    var area = document.getElementById('manual-leg-area');
    if (!area) return;
    var gd = currentGameData;
    var gameEvents = (gd && gd.gameEvents) || [];

    if (!gd || gameEvents.length === 0) {
        area.innerHTML = '';
        return;
    }

    var markets = gd.availableMarkets || [];
    var marketOptions = markets.map(function(m) {
        return '<option value="' + escapeAttr(m) + '">' + escapeAttr(shortMarketLabel(m)) + '</option>';
    }).join('');

    var gamePicker = '';
    if (gameEvents.length > 1) {
        var gameOptions = gameEvents.map(function(g) {
            return '<option value="' + escapeAttr(g.eventId) + '">' + escapeAttr(g.matchup) + '</option>';
        }).join('');
        gamePicker = '<select id="manual-game" style="width:auto;flex:1 1 220px;margin:0;">' + gameOptions + '</select>';
    }

    area.innerHTML = '<div class="entry-builder">'
        + '<strong>Add a manual/discounted pick</strong> '
        + '<span class="meta" style="margin:0;display:inline;">(for promos like "Taco Tuesday" discounts that PropLine\'s feed doesn\'t carry)</span>'
        + '<div style="margin-top:0.6rem;display:flex;gap:0.5rem;flex-wrap:wrap;align-items:flex-start;">'
        + gamePicker
        + '<input type="text" id="manual-player" placeholder="Player name (exact)" style="width:auto;flex:1 1 180px;margin:0;">'
        + '<select id="manual-market" style="width:auto;flex:1 1 160px;margin:0;">' + marketOptions + '</select>'
        + '<input type="number" step="0.5" id="manual-point" placeholder="Line, e.g. 62.5" style="width:auto;flex:0 1 120px;margin:0;">'
        + '<select id="manual-type" style="width:auto;flex:0 1 220px;margin:0;">'
        + '<option value="discount" selected>Discount promo (standard payout)</option>'
        + '<option value="standard">Standard (normal line)</option>'
        + '<option value="goblin">Goblin (reduced payout)</option>'
        + '<option value="demon">Demon (boosted payout)</option>'
        + '</select>'
        + '<button type="button" onclick="submitManualLeg()" style="margin:0;">Add &amp; grade</button>'
        + '</div>'
        + '<div id="manual-leg-result" class="mult-result"></div>'
        + '</div>';
}

function submitManualLeg() {
    var resultEl = document.getElementById('manual-leg-result');
    var gd = currentGameData;
    var gameEvents = (gd && gd.gameEvents) || [];
    if (!gd || gameEvents.length === 0) return;

    var gamePickerEl = document.getElementById('manual-game');
    var eventId = gamePickerEl ? gamePickerEl.value : gameEvents[0].eventId;
    var player = document.getElementById('manual-player').value.trim();
    var market = document.getElementById('manual-market').value;
    var point = parseFloat(document.getElementById('manual-point').value);
    var dfsType = document.getElementById('manual-type').value;

    if (!player) { resultEl.innerHTML = '<span style="color:var(--danger)">Enter a player name.</span>'; return; }
    if (!market) { resultEl.innerHTML = '<span style="color:var(--danger)">Pick a market.</span>'; return; }
    if (isNaN(point)) { resultEl.innerHTML = '<span style="color:var(--danger)">Enter a valid line.</span>'; return; }

    resultEl.innerHTML = spinnerHtml('Grading...');
    fetch('/grade_manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            sport: gd.sport, event_id: eventId,
            player: player, market: market, point: point, dfs_type: dfsType
        })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (!data.success) {
            resultEl.innerHTML = '<span style="color:var(--danger)">' + data.message + '</span>';
            return;
        }
        var matchedGame = gameEvents.filter(function(g) { return g.eventId === eventId; })[0];
        if (matchedGame) data.row.matchup = matchedGame.matchup;
        addManualLegRow(data.row);
        resultEl.innerHTML = '<span style="color:var(--success)">Added -- see it in the results below.</span>';
    })
    .catch(function(err) {
        resultEl.innerHTML = '<span style="color:var(--danger)">Request failed: ' + err + '</span>';
    });
}

function addManualLegRow(row) {
    var games = loadGames();
    var gd = games[currentGameData.gameKey];
    if (!gd) return;

    // Replace any existing row for the same player/market/point instead of
    // duplicating it, e.g. re-adding after picking a different dfs_type.
    // Manual picks go to the front -- rows render in array order (see
    // colHtml in renderFilteredColumns), and a manual pick you just added
    // should be immediately visible, not buried under everything scanned.
    var idx = gd.rows.findIndex(function(r) {
        return r.player === row.player && r.market === row.market && r.point === row.point;
    });
    if (idx !== -1) gd.rows.splice(idx, 1);
    gd.rows.unshift(row);

    if (saveGames(games)) {
        currentGameData = gd;
        renderFilteredColumns();
    } else {
        alert('Could not save this pick -- browser storage is full.');
    }
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
        return list.map(function(r) { return legRowHtml(withBoost(r), gameKey, gameLabel, allRows.indexOf(r)); }).join('');
    }

    var barText = profitBoostPct
        ? (gameData.bar + '% → ' + withBoost({ bar: gameData.bar }).bar + '% with ' + profitBoostPct + '% boost')
        : (gameData.bar + '%');
    var metaText = rows.length === allRows.length
        ? (allRows.length + ' legs scanned | break-even bar: ' + barText)
        : (rows.length + ' of ' + allRows.length + ' legs shown | break-even bar: ' + barText);

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

function selectQualifyingTiers() {
    if (!currentGameData) return;
    var gameKey = currentGameData.gameKey;
    var gameLabel = currentGameData.label;
    var qualifying = { 'TIER S': true, 'TIER A': true, 'TIER B': true };
    var added = 0;

    currentGameData.rows.filter(matchesFilters).map(withBoost).forEach(function(r) {
        var hasData = r.consensus_pct !== null && r.consensus_pct !== undefined;
        if (!hasData || !qualifying[r.tier]) return;

        var legId = gameKey + '::' + r.player + '::' + r.market + '::' + r.point;
        if (selectedLegs[legId]) return; // already selected

        var shortMarket = shortMarketLabel(r.market);
        selectedLegs[legId] = {
            label: r.player + ' - ' + r.side + ' ' + shortMarket + ' ' + r.point,
            consensus_pct: r.consensus_pct,
            gameLabel: gameLabel,
            fullData: {
                player: r.player, market: r.market, point: r.point, side: r.side,
                dfs_type: r.dfs_type, consensus_pct: r.consensus_pct, bar: r.bar, margin: r.margin,
                tier: r.tier, whole_number: (r.point !== null && r.point % 1 === 0),
                estimate_type: r.estimate_type, book_point: r.book_point,
                over_price: r.over_price, under_price: r.under_price,
                books: r.books, matchup: r.matchup || '', spread_pct: r.spread_pct,
                sport: r.sport || '', event_id: r.eventId || '',
            },
        };
        added++;
    });

    saveSelected();
    renderEntryBuilder();
    renderFilteredColumns();
    if (added === 0) {
        alert('No new Tier A/B/S picks to add from this tab -- either none currently qualify (respecting active filters/boost), or they\'re already selected.');
    }
}

function renderEntryBuilder() {
    var area = document.getElementById('entry-builder-area');
    var legIds = Object.keys(selectedLegs);
    var autoSelectBtn = '<button type="button" class="browse-btn" onclick="selectQualifyingTiers()" style="margin-bottom:0.6rem;">'
        + 'Select all Tier A/B/S from this tab</button>';

    // Re-rendering (e.g. toggling Entry type) would otherwise wipe whatever
    // the user already typed into these -- carry them forward across re-renders.
    var prevMultEl = document.getElementById('entry-mult');
    var prevMult = prevMultEl ? prevMultEl.value : '';
    var prevOneMissEl = document.getElementById('entry-mult-1miss');
    var prevOneMiss = prevOneMissEl ? prevOneMissEl.value : '';
    var prevTwoMissEl = document.getElementById('entry-mult-2miss');
    var prevTwoMiss = prevTwoMissEl ? prevTwoMissEl.value : '';

    if (legIds.length === 0) {
        area.innerHTML = '<div class="entry-builder">' + autoSelectBtn
            + '<div><strong>Build an entry:</strong> check legs '
            + '(from any game/tab) to combine them here -- selections carry across tabs.</div></div>';
        return;
    }

    var listHtml = legIds.map(function(legId) {
        var leg = selectedLegs[legId];
        return '<div class="selected-leg" data-legid="' + escapeAttr(legId) + '" onclick="removeLeg(this.dataset.legid)" title="Click to remove">'
            + '<span>' + leg.label + ' <span class="meta">(' + leg.gameLabel + ')</span></span>'
            + '<span class="tab-close">&times;</span>'
            + '</div>';
    }).join('');

    var n = legIds.length;
    var typeSelectEl = document.getElementById('log-entry-type');
    var isFlex = typeSelectEl ? typeSelectEl.value === 'Flex' : false;
    var showFlexTiers = isFlex && n >= 3;
    var flexDefaults = FLEX_PAYOUT_DEFAULTS[n] || { oneMiss: null, twoMiss: null };

    var flexTierFieldsHtml = '';
    if (showFlexTiers) {
        var oneMissVal = prevOneMiss !== '' ? prevOneMiss : (flexDefaults.oneMiss != null ? flexDefaults.oneMiss : '');
        var twoMissVal = prevTwoMiss !== '' ? prevTwoMiss : flexDefaults.twoMiss;
        flexTierFieldsHtml = '<div style="margin-top:0.5rem;">'
            + (n - 1) + ' of ' + n + ' hit pays: '
            + '<input type="number" step="0.01" min="0" id="entry-mult-1miss" placeholder="e.g. 1.5" '
            + 'value="' + oneMissVal + '" oninput="calcEntry()" style="width:100px;display:inline-block;margin:0 0 0.5rem 0.4rem;">'
            + (flexDefaults.twoMiss != null
                ? '<br>' + (n - 2) + ' of ' + n + ' hit pays: '
                    + '<input type="number" step="0.01" min="0" id="entry-mult-2miss" placeholder="e.g. 0.4" '
                    + 'value="' + twoMissVal + '" oninput="calcEntry()" style="width:100px;display:inline-block;margin:0 0 0.5rem 0.4rem;">'
                : '')
            + '<div class="meta">Defaults from the reference chart -- multipliers can vary by lineup/promos, '
            + 'edit these to match the real numbers shown in the app for this entry.</div>'
            + '</div>';
    }

    var html = '<div class="entry-builder">'
        + autoSelectBtn
        + '<strong>Building entry (' + n + ' leg' + (n > 1 ? 's' : '') + '):</strong>'
        + '<div style="margin: 0.4rem 0;">' + listHtml + '</div>'
        + '<div>Entry type: '
        + '<select id="log-entry-type" onchange="renderEntryBuilder()"><option value="Power"' + (isFlex ? '' : ' selected') + '>Power</option>'
        + '<option value="Flex"' + (isFlex ? ' selected' : '') + '>Flex</option></select>'
        + '</div>'
        + '<div style="margin-top:0.5rem;">' + (isFlex ? 'All ' + n + ' hit pays' : 'Real payout multiplier') + ': '
        + '<input type="number" step="0.01" min="0.01" id="entry-mult" placeholder="e.g. 2.3" value="' + prevMult + '" oninput="calcEntry()">'
        + '</div>'
        + flexTierFieldsHtml
        + '<div id="entry-result" class="mult-result"></div>'
        + '<button type="button" class="log-parlay-btn" onclick="logParlay()">Log this parlay</button>'
        + '<div id="log-parlay-result" class="mult-result"></div>'
        + '<div style="margin-top:0.7rem;padding-top:0.7rem;border-top:1px solid var(--border);">'
        + '<button type="button" class="browse-btn" onclick="logLegsForTracking()">'
        + 'Log these legs for tracking only (no multiplier)</button>'
        + '<div class="meta" style="margin-top:0.3rem;">Records each leg\'s tier and probability now -- '
        + 'fill in Result (W/L) in the spreadsheet later to check whether tiers actually predict hit rate.</div>'
        + '<div id="log-tracking-result" class="mult-result"></div>'
        + '</div>'
        + (legIds.length >= 2
            ? '<div style="margin-top:0.7rem;padding-top:0.7rem;border-top:1px solid var(--border);">'
                + '<button type="button" class="browse-btn" onclick="checkEntryCorrelation()">Check correlation (AI)</button>'
                + '<div class="meta" style="margin-top:0.3rem;">Advisory only -- flags real relationships between legs '
                + '(same game, related stats) in plain language. Never recalculates the combined probability above.</div>'
                + '<div id="correlation-result" style="display:none;margin-top:0.4rem;"></div>'
                + '</div>'
            : '')
        + '</div>';
    area.innerHTML = html;
    calcEntry();
}

function checkEntryCorrelation() {
    var resultEl = document.getElementById('correlation-result');
    if (!resultEl) return;

    var legs = Object.keys(selectedLegs).map(function(legId) {
        var d = selectedLegs[legId].fullData || {};
        return {
            player: d.player, matchup: d.matchup,
            market_label: shortMarketLabel(d.market || ''),
            side: d.side, point: d.point,
        };
    });

    resultEl.style.display = 'block';
    resultEl.innerHTML = spinnerHtml('Checking (this calls out to Gemini, may take a few seconds)...');

    fetch('/check_correlation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ legs: legs })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (!data.success) {
            resultEl.innerHTML = '<div class="game-list-msg" style="color:var(--danger)">' + data.text + '</div>';
            return;
        }
        resultEl.innerHTML = '<pre class="raw-json">' + escapeAttr(data.text) + '</pre>';
    })
    .catch(function(err) {
        resultEl.innerHTML = '<div class="game-list-msg" style="color:var(--danger)">Request failed: ' + err + '</div>';
    });
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
    var isFlex = typeSelect && typeSelect.value === 'Flex' && legIds.length >= 3;
    var entryTypeLabel = legIds.length + '-' + (typeSelect ? typeSelect.value : 'Power');
    var today = new Date().toISOString().slice(0, 10);

    var oneMissEl = document.getElementById('entry-mult-1miss');
    var twoMissEl = document.getElementById('entry-mult-2miss');
    var oneMissMultiplier = isFlex && oneMissEl ? parseFloat(oneMissEl.value) : null;
    var twoMissMultiplier = isFlex && twoMissEl ? parseFloat(twoMissEl.value) : null;
    if (isNaN(oneMissMultiplier)) oneMissMultiplier = null;
    if (isNaN(twoMissMultiplier)) twoMissMultiplier = null;

    resultEl.innerHTML = spinnerHtml('Logging...');
    fetch('/log_parlay', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            legs: legsForLog, multiplier: m, entry_type_label: entryTypeLabel, date: today,
            is_flex: isFlex, one_miss_multiplier: oneMissMultiplier, two_miss_multiplier: twoMissMultiplier
        })
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

function logLegsForTracking() {
    var resultEl = document.getElementById('log-tracking-result');
    var legIds = Object.keys(selectedLegs);
    var legsForLog = legIds.map(function(legId) { return selectedLegs[legId].fullData; })
        .filter(function(d) { return d && d.player; });

    if (legsForLog.length === 0) {
        resultEl.innerHTML = '<span style="color:var(--danger)">No loggable leg data found -- try re-selecting the legs.</span>';
        return;
    }

    var today = new Date().toISOString().slice(0, 10);

    resultEl.innerHTML = spinnerHtml('Logging...');
    fetch('/log_tracking', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ legs: legsForLog, date: today })
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
    if (legIds.length === 0) {
        resultEl.innerHTML = '';
        return;
    }

    var probs = legIds.map(function(legId) { return selectedLegs[legId].consensus_pct / 100.0; });
    var n = probs.length;
    var allHitProb = probs.reduce(function(acc, p) { return acc * p; }, 1.0);
    var allHitPct = (allHitProb * 100).toFixed(1);

    var m = parseFloat(multEl.value);
    if (!m || m <= 0) {
        resultEl.innerHTML = 'Probability all ' + n + ' hit: ' + allHitPct
            + '%. Enter the real payout multiplier above to see if it clears break-even.';
        return;
    }

    var typeSelectEl = document.getElementById('log-entry-type');
    var isFlex = typeSelectEl && typeSelectEl.value === 'Flex' && n >= 3;

    var ev, breakdownLine;
    if (!isFlex) {
        // Power (or too few legs to be a real Flex): true all-or-nothing,
        // required probability is just 1/multiplier.
        ev = allHitProb * m;
        breakdownLine = 'Required (1/multiplier): ' + (100.0 / m).toFixed(1) + '%';
    } else {
        // Flex pays out at multiple hit-count tiers (e.g. a 4-pick Flex
        // still pays 1.5x on 3 of 4 hit, not $0) -- computing EV off only
        // the all-hit probability, like Power, throws away real value from
        // those lower tiers and understates a Flex entry's true edge. Uses
        // each leg's own real probability (Poisson binomial), not the
        // equal-probability approximation the static reference chart uses.
        var dist = poissonBinomialDist(probs);
        var oneMissEl = document.getElementById('entry-mult-1miss');
        var oneMissM = oneMissEl ? parseFloat(oneMissEl.value) : NaN;
        var twoMissEl = document.getElementById('entry-mult-2miss');
        var twoMissM = twoMissEl ? parseFloat(twoMissEl.value) : NaN;

        ev = dist[n] * m;
        breakdownLine = 'P(all ' + n + ' hit): ' + (dist[n] * 100).toFixed(1) + '%';
        if (!isNaN(oneMissM) && oneMissM > 0) {
            ev += dist[n - 1] * oneMissM;
            breakdownLine += ' | P(' + (n - 1) + ' of ' + n + '): ' + (dist[n - 1] * 100).toFixed(1) + '%';
        }
        if (twoMissEl && !isNaN(twoMissM) && twoMissM > 0) {
            ev += dist[n - 2] * twoMissM;
            breakdownLine += ' | P(' + (n - 2) + ' of ' + n + '): ' + (dist[n - 2] * 100).toFixed(1) + '%';
        }
    }

    var marginPts = (ev - 1.0) * 100;
    var tier = tierForMargin(marginPts);
    var TIER_COLOR = { 'TIER S': 'var(--success)', 'TIER A': 'var(--accent)', 'TIER B': 'var(--warning)', 'TIER C': 'var(--text-secondary)' };
    var color = TIER_COLOR[tier] || 'var(--text-muted)';
    resultEl.innerHTML = 'Probability all ' + n + ' hit: ' + allHitPct + '% | ' + breakdownLine + '<br>'
        + 'Modelled EV: ' + ev.toFixed(3) + 'x | Edge margin: ' + (marginPts >= 0 ? '+' : '') + marginPts.toFixed(1) + ' pts | '
        + '<strong style="color:' + color + '">' + tier + '</strong>';
}

// ---- Page load: merge any new scan into storage, then render from storage ----
(function() {
    try {
        if (localStorage.getItem(BREAKEVEN_EXPANDED_KEY) === '1') {
            var body = document.getElementById('breakeven-chart-body');
            var chevron = document.getElementById('breakeven-chevron');
            if (body) body.style.display = 'block';
            if (chevron) chevron.textContent = '▾';
        }
    } catch (e) { /* ignore */ }

    var payloadEl = document.getElementById('scan-payload');
    var games = loadGames();
    var activeKey = localStorage.getItem(ACTIVE_KEY);
    selectedLegs = loadSelected();

    if (payloadEl) {
        try {
            var payload = JSON.parse(payloadEl.textContent);
            var newKey = payload.gameKey;
            games[newKey] = payload;

            if (!saveGames(games)) {
                // Storage is full -- evict older tabs (oldest saved first, never
                // the new one) until it fits, instead of failing outright.
                var otherKeys = Object.keys(games).filter(function(k) { return k !== newKey; });
                var fitted = false;
                for (var i = 0; i < otherKeys.length; i++) {
                    delete games[otherKeys[i]];
                    if (saveGames(games)) { fitted = true; break; }
                }
                if (!fitted) {
                    delete games[newKey];
                    games = loadGames();
                    alert('This scan is too large to save as a tab, even after clearing older '
                        + 'saved games (browser storage limit). Try a smaller slate or a single game instead.');
                }
            }

            if (games[newKey]) {
                activeKey = newKey;
                localStorage.setItem(ACTIVE_KEY, activeKey);
            }
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
