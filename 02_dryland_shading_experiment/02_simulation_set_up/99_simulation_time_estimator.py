#!/usr/bin/env python3
"""Live APSIM throughput and site completion forecasts for SLURM job 1064365."""
import csv
import glob
import heapq
import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from bisect import bisect_right
from datetime import datetime, timedelta
from statistics import median

JOB_ID = '1064365'
LOG_DIR = ('$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/'
           '02_dryland_shading_experiment/02_simulation_set_up/'
           'logs/05_apsim_sims_timing_logs')
SITES = ['birchip', 'bordertown', 'lakebolac', 'lameroo',
         'longerenong', 'mildura', 'millicent', 'waikerie']
PER_SITE = 86040
PER_TASK = 700
TOTAL = PER_SITE * len(SITES)
N_TASKS = math.ceil(TOTAL / PER_TASK)
WINDOWS = [('8 hours', 480), ('4 hours', 240), ('2 hours', 120),
           ('1 hour', 60), ('30 minutes', 30), ('10 minutes', 10)]


def task_parts(task_id):
    first = task_id * PER_TASK
    last = min(first + PER_TASK, TOTAL)
    parts = []
    while first < last:
        idx = first // PER_SITE
        boundary = min(last, (idx + 1) * PER_SITE)
        parts.append((SITES[idx], boundary - first))
        first = boundary
    return parts


def read_slurm():
    command = ['squeue', '-h', '-j', JOB_ID, '-t', 'R', '-o', '%i|%N']
    try:
        output = subprocess.check_output(command, text=True, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'Unable to query SLURM: {exc}')
    running = {}
    for line in output.splitlines():
        fields = line.strip().split('|')
        if len(fields) == 2:
            match = re.fullmatch(re.escape(JOB_ID) + r'_(\d+)', fields[0])
            if match:
                running[int(match.group(1))] = fields[1]
    return running


def parse_slurm_time(value):
    value = (value or '').strip()
    if not value or value in ('Unknown', 'None', 'N/A'):
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None


def read_node_history(running, now):
    """Recover node assignments and task intervals from SLURM accounting.

    Intervals are clipped to now for still-running tasks. Accounting may lag.
    """
    nodes = dict(running)
    intervals = {}
    try:
        output = subprocess.check_output(
            ['sacct', '-n', '-P', '-j', JOB_ID,
             '--format=JobIDRaw,NodeList,State,Start,End'],
            text=True, stderr=subprocess.PIPE, timeout=45)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return nodes, intervals, False
    for line in output.splitlines():
        fields = line.split('|')
        if len(fields) < 5:
            continue
        match = re.fullmatch(re.escape(JOB_ID) + r'_(\d+)', fields[0].strip())
        if not match:
            continue
        task_id = int(match.group(1))
        node = fields[1].strip()
        if (not node or node in ('None', 'Unknown', 'None assigned', 'N/A')
                or node.startswith('(') or ',' in node or '[' in node):
            continue
        nodes[task_id] = node
        start = parse_slurm_time(fields[3])
        end = parse_slurm_time(fields[4]) or now
        if start and start <= now and end > start:
            intervals[task_id] = (node, start, min(end, now))
    return nodes, intervals, True


def build_concurrency_index(intervals):
    """Stepwise node concurrency from task start/end events."""
    changes = defaultdict(list)
    for node, start, end in intervals.values():
        changes[node].append((start, 1))
        changes[node].append((end, -1))
    result = {}
    for node, events in changes.items():
        events.sort(key=lambda item: (item[0], item[1]))
        times, levels = [], []
        level = 0
        for stamp, delta in events:
            level += delta
            times.append(stamp)
            levels.append(level)
        result[node] = (times, levels)
    return result


def concurrency_at(index, node, stamp):
    times, levels = index.get(node, ([], []))
    i = bisect_right(times, stamp) - 1
    return levels[i] if i >= 0 else 0


def concurrency_band(n):
    if n < 1:
        return None
    if n <= 5:
        return '1-5'
    if n <= 10:
        return '6-10'
    if n <= 15:
        return '11-15'
    if n <= 20:
        return '16-20'
    if n <= 30:
        return '21-30'
    if n <= 40:
        return '31-40'
    return '41+'


def main():
    now = datetime.now()
    running = read_slurm()
    task_nodes, task_intervals, sacct_available = read_node_history(running, now)
    concurrency_index = build_concurrency_index(task_intervals)
    concurrency_samples = defaultdict(list)  # (node, site, band) -> durations
    concurrency_recent = defaultdict(list)   # (node, site, band) -> (end, duration)
    counts = defaultdict(Counter)
    site_speeds = defaultdict(list)
    node_speeds = defaultdict(list)
    pair_speeds = defaultdict(list)
    all_speeds = []
    processed = defaultdict(int)
    end_times = []
    site_end_times = defaultdict(list)
    node_events = defaultdict(list)  # (end_time, duration, site) per node
    invalid_timestamps = 0
    extra_rows = 0
    log_files = glob.glob(os.path.join(LOG_DIR, f'timing_task_{JOB_ID}_*.csv'))

    for path in log_files:
        match = re.search(r'_(\d+)\.csv$', path)
        if not match:
            continue
        task_id = int(match.group(1))
        if not 0 <= task_id < N_TASKS:
            continue
        expected = sum(n for _, n in task_parts(task_id))
        node = task_nodes.get(task_id)
        try:
            with open(path, newline='') as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if processed[task_id] >= expected:
                        extra_rows += 1
                        continue
                    name = (row.get('site') or '').lower()
                    site = next((s for s in SITES if name.startswith(s + '_')), None)
                    if site is None:
                        continue
                    status = (row.get('status') or '').upper()
                    if not status:
                        continue
                    processed[task_id] += 1
                    counts[site][status] += 1
                    try:
                        finished = datetime.fromisoformat(row['end_time'].strip())
                        if finished.tzinfo is not None:
                            finished = finished.astimezone().replace(tzinfo=None)
                        if finished <= now:
                            end_times.append(finished)
                            site_end_times[site].append(finished)
                            if node:
                                try:
                                    duration_for_event = float(row['duration_seconds'])
                                except (ValueError, KeyError, TypeError):
                                    duration_for_event = None
                                node_events[node].append((finished, duration_for_event, site))
                                if duration_for_event is not None and duration_for_event > 0:
                                    sim_start = finished - timedelta(seconds=duration_for_event)
                                    midpoint = sim_start + timedelta(seconds=duration_for_event / 2)
                                    concurrent = concurrency_at(concurrency_index, node, midpoint)
                                    band = concurrency_band(concurrent)
                                    if band:
                                        concurrency_samples[(node, site, band)].append(duration_for_event)
                                        concurrency_recent[(node, site, band)].append((finished, duration_for_event))
                    except (ValueError, KeyError, AttributeError):
                        invalid_timestamps += 1
                    try:
                        duration = float(row['duration_seconds'])
                    except (ValueError, KeyError, TypeError):
                        continue
                    if duration > 0 and status == 'SUCCESS':
                        site_speeds[site].append(duration)
                        all_speeds.append(duration)
                        if node:
                            pair_speeds[(site, node)].append(duration)
                            node_speeds[node].append(duration)
        except OSError as exc:
            print(f'Warning: could not read {path}: {exc}')

    def seconds_per_sim(site, node):
        for values in (pair_speeds[(site, node)], node_speeds[node],
                       site_speeds[site], all_speeds):
            if len(values) >= 10:
                return median(values)
        return 25.0

    def remaining_parts(task_id):
        skipped = processed[task_id]
        result = []
        for site, n in task_parts(task_id):
            left = max(0, n - skipped)
            skipped = max(0, skipped - n)
            if left:
                result.append((site, left))
        return result

    remaining = Counter()
    site_finish = {site: now for site in SITES}
    for task_id in range(N_TASKS):
        for site, n in remaining_parts(task_id):
            remaining[site] += n

    slots = []
    for task_id, node in running.items():
        elapsed = 0.0
        for site, n in remaining_parts(task_id):
            elapsed += n * seconds_per_sim(site, node)
            site_finish[site] = max(site_finish[site], now + timedelta(seconds=elapsed))
        heapq.heappush(slots, (elapsed, task_id, node))

    pending = [task_id for task_id in range(N_TASKS)
               if task_id not in running and processed[task_id] == 0]
    if pending and not slots:
        print('WARNING: No running slots; cannot forecast pending task start times.')
    else:
        for task_id in pending:
            available, _, node = heapq.heappop(slots)
            elapsed = available
            for site, n in remaining_parts(task_id):
                elapsed += n * seconds_per_sim(site, node)
                site_finish[site] = max(site_finish[site], now + timedelta(seconds=elapsed))
            heapq.heappush(slots, (elapsed, task_id, node))

    attempted = sum(sum(c.values()) for c in counts.values())
    print(f'\nAPSIM FORECAST | {now:%Y-%m-%d %H:%M:%S}')
    print('Estimator version: 2.3 (includes historical node concurrency analysis)')
    print(f'Running SLURM tasks: {len(running)}')
    print(f'Tasks expected: {N_TASKS}')
    print(f'Simulations expected: {TOTAL:,}')
    print(f'Simulation records found: {attempted:,}')
    print('\nSITE COMPLETION FORECAST (task-aware)')
    print(f"{'Site':<15} {'Success':>9} {'Failed':>8} {'Remaining':>10} {'Estimated completion':>23}")
    print('-' * 73)
    for site in SITES:
        success = counts[site]['SUCCESS']
        failed = sum(n for status, n in counts[site].items() if status != 'SUCCESS')
        print(f'{site:<15} {success:>9,} {failed:>8,} {remaining[site]:>10,} '
              f'{site_finish[site]:%a %d %b %H:%M}')

    print('\nRECENT SIMULATION THROUGHPUT (all sites; completed attempts)')
    print(f"{'Window':<13} {'Processed':>11} {'Sims/hour':>13} {'vs 8h rate':>13}")
    print('-' * 54)
    window_results = []
    for label, minutes in WINDOWS:
        cutoff = now - timedelta(minutes=minutes)
        n = sum(cutoff <= t <= now for t in end_times)
        rate = n * 60 / minutes
        window_results.append((label, n, rate))
    baseline = window_results[0][2]
    for label, n, rate in window_results:
        comparison = f'{(rate / baseline - 1) * 100:+.1f}%' if baseline else 'N/A'
        print(f'{label:<13} {n:>11,} {rate:>13,.1f} {comparison:>13}')

    print('\nPER-SITE RECENT THROUGHPUT (completed attempts)')
    print(f"{'Site':<15} {'Last 1h':>10} {'Sims/hour':>12} "
          f"{'Last 10m':>10} {'Sims/hour':>12} {'10m vs 1h':>12}")
    print('-' * 77)
    one_hour_cutoff = now - timedelta(hours=1)
    ten_minute_cutoff = now - timedelta(minutes=10)
    for site in SITES:
        times = site_end_times[site]
        count_1h = sum(one_hour_cutoff <= t <= now for t in times)
        count_10m = sum(ten_minute_cutoff <= t <= now for t in times)
        rate_1h = float(count_1h)
        rate_10m = count_10m * 6.0
        comparison = (f'{(rate_10m / rate_1h - 1) * 100:+.1f}%'
                      if rate_1h > 0 else 'N/A')
        print(f'{site:<15} {count_1h:>10,} {rate_1h:>12,.1f} '
              f'{count_10m:>10,} {rate_10m:>12,.1f} {comparison:>12}')
    print('A 10m vs 1h change can reflect tasks moving between sites,')
    print('not necessarily a change in processing speed.')

    print('\nPER-NODE PERFORMANCE (last 1 hour vs last 10 minutes)')
    print(f"{'Node':<15} {'Running':>7} {'1h count':>10} {'10m count':>10} "
          f"{'1h sims/h':>11} {'10m sims/h':>12} {'Rate change':>12}")
    print('-' * 85)
    current_node_counts = Counter(running.values())
    for node in sorted(set(node_events) | set(current_node_counts)):
        events = node_events[node]
        one_h = [e for e in events if one_hour_cutoff <= e[0] <= now]
        ten_m = [e for e in events if ten_minute_cutoff <= e[0] <= now]
        rate_h = float(len(one_h))
        rate_m = len(ten_m) * 6.0
        change = f'{(rate_m / rate_h - 1) * 100:+.1f}%' if rate_h else 'N/A'
        print(f'{node:<15} {current_node_counts[node]:>7} {len(one_h):>10,} '
              f'{len(ten_m):>10,} {rate_h:>11,.1f} {rate_m:>12,.1f} {change:>12}')

    print('\nPER-NODE SIMULATION DURATION (last 1 hour vs last 10 minutes)')
    print(f"{'Node':<15} {'1h median(s)':>14} {'10m median(s)':>15} "
          f"{'Duration change':>16} {'1h samples':>12} {'10m samples':>12}")
    print('-' * 90)
    for node in sorted(set(node_events) | set(current_node_counts)):
        events = node_events[node]
        d_h = [e[1] for e in events if one_hour_cutoff <= e[0] <= now
               and e[1] is not None and e[1] > 0]
        d_m = [e[1] for e in events if ten_minute_cutoff <= e[0] <= now
               and e[1] is not None and e[1] > 0]
        m_h = median(d_h) if d_h else None
        m_m = median(d_m) if d_m else None
        change = (f'{(m_m / m_h - 1) * 100:+.1f}%'
                  if m_h is not None and m_m is not None else 'N/A')
        print(f'{node:<15} {f"{m_h:.1f}" if m_h is not None else "N/A":>14} '
              f'{f"{m_m:.1f}" if m_m is not None else "N/A":>15} '
              f'{change:>16} {len(d_h):>12,} {len(d_m):>12,}')
    print('Positive duration change means slower individual simulations.')
    print('Node throughput can change when the number of active tasks changes.')
    print('Median duration can change when the mix of sites/simulations changes.')
    if not sacct_available:
        print('WARNING: sacct unavailable; completed tasks cannot be assigned to nodes.')
    elif len(task_nodes) < N_TASKS:
        print(f'NOTE: Node known for {len(task_nodes)} of {N_TASKS} tasks; '
              'unmapped historical records are excluded from per-node tables.')

    print('\nHISTORICAL NODE CONCURRENCY VS SIMULATION DURATION')
    print('Tasks = simultaneous array tasks on the same node at simulation midpoint.')
    print('Duration grouped by node, site and concurrency band (controls for site mix).')
    print(f"{'Node':<14} {'Site':<14} {'Tasks':>7} {'Samples':>9} "
          f"{'Median(s)':>11} {'Last 1h(s)':>12} {'Last 10m(s)':>13}")
    print('-' * 86)
    band_order = ['1-5', '6-10', '11-15', '16-20', '21-30', '31-40', '41+']
    shown = 0
    for node in sorted({key[0] for key in concurrency_samples}):
        for site in SITES:
            for band in band_order:
                key = (node, site, band)
                values = concurrency_samples.get(key, [])
                if not values:
                    continue
                recent = concurrency_recent[key]
                hour = [d for t, d in recent if one_hour_cutoff <= t <= now]
                ten = [d for t, d in recent if ten_minute_cutoff <= t <= now]
                fmt = lambda v: f'{median(v):.1f}' if v else 'N/A'
                print(f'{node:<14} {site:<14} {band:>7} {len(values):>9,} '
                      f'{fmt(values):>11} {fmt(hour):>12} {fmt(ten):>13}')
                shown += 1
    if not shown:
        print('No concurrency samples available: check sacct Start/End availability.')
    print('Compare rows for the SAME node and site across different task-count bands.')
    print('At least ~30 samples per band is preferable; small groups are noisy.')
    print('Association is not proof of causation: workload and other users may vary.')
    print(f'SLURM task intervals recovered: {len(task_intervals)} / {N_TASKS}.')
    if len(task_intervals) < len(task_nodes):
        print('WARNING: Missing intervals exclude some simulations from concurrency analysis.')

    # A second, simple forecast based on the latest hour's overall output rate.
    # It does not model site differences or straggling tasks.
    recent_rate = window_results[3][2]
    print('\nRECENT-RATE FORECAST (last 1 hour; assumes constant overall rate)')
    if recent_rate <= 0:
        print('No simulations completed in the last hour; ETA unavailable.')
    else:
        cumulative = 0
        for site in SITES:
            cumulative += remaining[site]
            eta = now + timedelta(hours=cumulative / recent_rate)
            print(f'{site:<15} {eta:%a %d %b %H:%M}')

    if invalid_timestamps:
        print(f'\nWARNING: {invalid_timestamps} records lacked a valid end_time.')
    if extra_rows:
        print(f'WARNING: {extra_rows} rows exceeded expected task capacities.')
    print('\nNOTE: Failed attempts count as processed, not successful.')
    print('Task-aware forecast assumes pending tasks start in task-ID order.')
    print('Recent-rate forecast assumes a constant throughput across future sites.')
    print('Throughput windows overlap and use simulation end_time, not task end_time.')
    print('Node speeds are estimated from available timing records.\n')


if __name__ == '__main__':
    main()
