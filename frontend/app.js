const { createApp, ref, computed, onMounted } = Vue;

createApp({
    setup() {
        const API_BASE = window.location.origin + '/api';

        // Theme
        const selectedTheme = ref(localStorage.getItem('theme') || 'redhat');

        // Filters
        const availableTags = ref([]);
        const selectedTag   = ref('');
        const timePreset    = ref('last-month');
        const resolution    = ref('monthly');
        const startDate     = ref('');
        const endDate       = ref('');
        const currency      = ref('USD');

        // Data
        const costData        = ref(null);
        const drillDownData   = ref(null);
        const selectedGroup   = ref(null); // group row from costData when drilling down

        // UI
        const loading         = ref(false);
        const loadingDrillDown = ref(false);
        const error           = ref(null);
        const currentView     = ref('dashboard'); // 'dashboard' | 'drilldown'
        const activeTab       = ref('overview');

        // Accordion state for project resource details
        const expandedProjects         = ref({}); // { projectName: bool }
        const projectResources         = ref({}); // { projectName: ResourceData | null }
        const projectResourcesLoading  = ref({}); // { projectName: bool }
        const projectResourcesError    = ref({}); // { projectName: string | null }

        // Sorting state — both tables default to total_cost descending
        const dashboardSort  = ref({ col: 'total_cost', dir: 'desc' });
        const drilldownSort  = ref({ col: 'total_cost', dir: 'desc' });

        // ── Theme ───────────────────────────────────────────────────────────
        function changeTheme() {
            document.body.className = `theme-${selectedTheme.value}`;
            localStorage.setItem('theme', selectedTheme.value);
        }
        function initializeTheme() {
            document.body.className = `theme-${selectedTheme.value}`;
        }

        // ── Time helpers ─────────────────────────────────────────────────────
        function timeParams() {
            const params = {};
            if (timePreset.value === 'custom' && startDate.value && endDate.value) {
                params.start_date = startDate.value;
                params.end_date   = endDate.value;
            } else {
                const map = {
                    'last-month':    { units: 'month', value: -1 },
                    'last-3-days':   { units: 'day',   value: -3 },
                    'month-to-date': { units: 'month', value: -1 },
                };
                const p = map[timePreset.value];
                if (p) { params.time_scope_units = p.units; params.time_scope_value = p.value; }
            }
            return params;
        }

        // ── API calls ────────────────────────────────────────────────────────
        async function fetchTags() {
            try {
                const res  = await fetch(`${API_BASE}/tags`);
                if (!res.ok) throw new Error((await res.json().catch(() => ({}))).message || `HTTP ${res.status}`);
                const data = await res.json();
                availableTags.value = data.tags;
                if (availableTags.value.length > 0 && !selectedTag.value) {
                    selectedTag.value = availableTags.value[0];
                    await fetchCosts();
                } else if (availableTags.value.length === 0) {
                    error.value = 'No tags available from API.';
                }
            } catch (err) {
                console.error('fetchTags:', err);
                error.value = `Failed to load tags: ${err.message}. You can still type a tag manually.`;
                availableTags.value = ['owner', 'team', 'env', 'app', 'project'];
            }
        }

        async function fetchCosts() {
            if (!selectedTag.value) return;
            loading.value = true;
            error.value   = null;
            try {
                const params = new URLSearchParams({ tag_key: selectedTag.value, resolution: resolution.value, ...timeParams() });
                const res = await fetch(`${API_BASE}/costs?${params}`);
                if (!res.ok) throw new Error((await res.json()).message || `HTTP ${res.status}`);
                costData.value = await res.json();
            } catch (err) {
                console.error('fetchCosts:', err);
                error.value = `Failed to load cost data: ${err.message}`;
            } finally {
                loading.value = false;
            }
        }

        async function navigateToDrillDown(group) {
            selectedGroup.value   = group;
            currentView.value     = 'drilldown';
            activeTab.value       = 'overview';
            loadingDrillDown.value = true;
            drillDownData.value   = null;
            window.scrollTo(0, 0);

            try {
                const params = new URLSearchParams({
                    tag_key:   selectedTag.value,
                    tag_value: group.group_name,
                    resolution: resolution.value,
                    ...timeParams()
                });
                const res = await fetch(`${API_BASE}/costs/drilldown?${params}`);
                if (!res.ok) throw new Error((await res.json()).message || `HTTP ${res.status}`);
                drillDownData.value = await res.json();
            } catch (err) {
                console.error('drilldown:', err);
                error.value = `Failed to load project details: ${err.message}`;
                currentView.value = 'dashboard';
            } finally {
                loadingDrillDown.value = false;
            }
        }

        function goBack() {
            currentView.value          = 'dashboard';
            drillDownData.value        = null;
            selectedGroup.value        = null;
            expandedProjects.value     = {};
            projectResources.value     = {};
            projectResourcesLoading.value = {};
            projectResourcesError.value   = {};
        }

        // ── Project resource accordion ────────────────────────────────────────
        async function fetchProjectResources(project) {
            const name = project.project_name;
            // Skip if already cached (null means error, object means data)
            if (name in projectResources.value) return;

            projectResourcesLoading.value = { ...projectResourcesLoading.value, [name]: true };

            try {
                const params = new URLSearchParams({ project_name: name, ...timeParams() });
                const res = await fetch(`${API_BASE}/costs/project-resources?${params}`);
                if (!res.ok) throw new Error((await res.json().catch(() => ({}))).message || `HTTP ${res.status}`);
                const data = await res.json();
                projectResources.value = { ...projectResources.value, [name]: data };
            } catch (err) {
                console.error('fetchProjectResources:', err);
                projectResourcesError.value = { ...projectResourcesError.value, [name]: err.message };
                projectResources.value = { ...projectResources.value, [name]: null };
            } finally {
                projectResourcesLoading.value = { ...projectResourcesLoading.value, [name]: false };
            }
        }

        function toggleProjectExpand(project) {
            const name = project.project_name;
            const isExpanding = !expandedProjects.value[name];
            expandedProjects.value = { ...expandedProjects.value, [name]: isExpanding };
            if (isExpanding && !(name in projectResources.value)) {
                fetchProjectResources(project);
            }
        }

        // Re-fetch drilldown with current filters (called when date/resolution changes on detail page)
        async function refreshDrillDown() {
            if (!selectedGroup.value) return;
            loadingDrillDown.value = true;
            drillDownData.value = null;
            // Invalidate resource cache — time period changed so cached metrics are stale
            expandedProjects.value     = {};
            projectResources.value     = {};
            projectResourcesLoading.value = {};
            projectResourcesError.value   = {};
            try {
                const params = new URLSearchParams({
                    tag_key:   selectedTag.value,
                    tag_value: selectedGroup.value.group_name,
                    resolution: resolution.value,
                    ...timeParams()
                });
                const res = await fetch(`${API_BASE}/costs/drilldown?${params}`);
                if (!res.ok) throw new Error((await res.json()).message || `HTTP ${res.status}`);
                drillDownData.value = await res.json();
            } catch (err) {
                error.value = `Failed to refresh: ${err.message}`;
            } finally {
                loadingDrillDown.value = false;
            }
        }

        // ── Sorting ───────────────────────────────────────────────────────────
        function applySortRows(rows, sortState) {
            return [...rows].sort((a, b) => {
                const av = a[sortState.col] ?? '';
                const bv = b[sortState.col] ?? '';
                const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv;
                return sortState.dir === 'asc' ? cmp : -cmp;
            });
        }

        // Clicking the active column toggles direction; clicking a new column starts desc.
        function setDashboardSort(col) {
            dashboardSort.value = dashboardSort.value.col === col
                ? { col, dir: dashboardSort.value.dir === 'asc' ? 'desc' : 'asc' }
                : { col, dir: 'desc' };
        }

        function setDrilldownSort(col) {
            drilldownSort.value = drilldownSort.value.col === col
                ? { col, dir: drilldownSort.value.dir === 'asc' ? 'desc' : 'asc' }
                : { col, dir: 'desc' };
        }

        // Returns the indicator character for a column header.
        // sortState is the auto-unwrapped plain object when called from the template.
        function sortIndicator(sortState, col) {
            if (sortState.col !== col) return '⇅';
            return sortState.dir === 'asc' ? '↑' : '↓';
        }

        // ── Per-project cost distribution ─────────────────────────────────────
        // Source of truth: drilldown project costs (may differ from group-level aggregation).
        // Overhead from selectedGroup is distributed proportionally across actual project costs.
        const detailTotals = computed(() => {
            if (!drillDownData.value?.projects || !selectedGroup.value) return null;
            const baseCost     = drillDownData.value.projects.reduce((sum, p) => sum + p.cost, 0);
            const overheadShare = selectedGroup.value.overhead_share;
            const totalCost    = baseCost + overheadShare;
            return { baseCost, overheadShare, totalCost };
        });

        const sortedGroups = computed(() => {
            if (!costData.value?.groups) return [];
            return applySortRows(costData.value.groups, dashboardSort.value);
        });

        const projectsWithDistribution = computed(() => {
            if (!drillDownData.value?.projects || !detailTotals.value) return [];

            const { baseCost: totalBaseCost, overheadShare: groupOverhead, totalCost: grandTotal } = detailTotals.value;

            const mapped = drillDownData.value.projects.map(p => {
                const shareRatio    = totalBaseCost > 0 ? p.cost / totalBaseCost : 0;
                const overheadShare = groupOverhead * shareRatio;
                const totalCost     = p.cost + overheadShare;
                return {
                    ...p,
                    base_cost:         p.cost,
                    overhead_share:    overheadShare,
                    total_cost:        totalCost,
                    consumption_ratio: grandTotal > 0 ? totalCost / grandTotal : 0,
                };
            });

            return applySortRows(mapped, drilldownSort.value);
        });

        // ── Keyboard shortcuts ────────────────────────────────────────────────
        function handleKeydown(e) {
            if (e.key === 'Escape' && currentView.value === 'drilldown') goBack();
            if (e.key === 'r' && !e.target.matches('input,select,textarea')) { e.preventDefault(); fetchCosts(); }
        }

        // ── Event handlers ────────────────────────────────────────────────────
        function onTimePresetChange() {
            if (timePreset.value !== 'custom') { startDate.value = ''; endDate.value = ''; }
            fetchCosts();
        }

        // ── Formatters ────────────────────────────────────────────────────────
        function formatCurrency(value) {
            if (value == null) return 'N/A';
            const symbol = currency.value === 'EUR' ? '€' : '$';
            return `${symbol}${new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)}`;
        }

        function formatPercentage(value) {
            if (value == null) return 'N/A';
            return `${(value * 100).toFixed(1)}%`;
        }

        function formatResourceValue(value, units) {
            if (value == null) return 'N/A';
            const n = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value);
            return units ? `${n} ${units}` : n;
        }

        // ── Lifecycle ─────────────────────────────────────────────────────────
        onMounted(async () => {
            initializeTheme();
            await fetchTags();
            window.addEventListener('keydown', handleKeydown);
        });

        Vue.onUnmounted(() => window.removeEventListener('keydown', handleKeydown));

        return {
            selectedTheme, changeTheme,
            availableTags, selectedTag, timePreset, resolution, startDate, endDate, currency,
            costData, drillDownData, selectedGroup,
            loading, loadingDrillDown, error,
            currentView, activeTab,
            detailTotals, sortedGroups, projectsWithDistribution,
            fetchCosts, navigateToDrillDown, goBack, refreshDrillDown, onTimePresetChange,
            expandedProjects, projectResources, projectResourcesLoading, projectResourcesError,
            toggleProjectExpand,
            dashboardSort, setDashboardSort,
            drilldownSort, setDrilldownSort,
            sortIndicator,
            formatCurrency, formatPercentage, formatResourceValue,
        };
    }
}).mount('#app');
