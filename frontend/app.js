/**
 * Cost Management Redux - Vue.js Application
 *
 * Frontend dashboard for displaying distributed cost data with dual-theme support.
 */

const { createApp, ref, computed, onMounted } = Vue;

createApp({
    setup() {
        // Configuration
        const API_BASE = window.location.origin + '/api';

        // State - Theme
        const selectedTheme = ref(localStorage.getItem('theme') || 'redhat');

        // State - Filters
        const availableTags = ref([]);
        const selectedTag = ref('');
        const timePreset = ref('last-month');
        const resolution = ref('monthly');
        const startDate = ref('');
        const endDate = ref('');
        const currency = ref('USD');

        // State - Data
        const costData = ref(null);
        const drillDownData = ref(null);

        // State - UI
        const loading = ref(false);
        const loadingDrillDown = ref(false);
        const error = ref(null);
        const showModal = ref(false);

        // Theme Management
        function changeTheme() {
            document.body.className = `theme-${selectedTheme.value}`;
            localStorage.setItem('theme', selectedTheme.value);
        }

        // Initialize theme on mount
        function initializeTheme() {
            document.body.className = `theme-${selectedTheme.value}`;
        }

        // API Calls
        async function fetchTags() {
            try {
                const response = await fetch(`${API_BASE}/tags`);
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.message || `HTTP ${response.status}`);
                }

                const data = await response.json();
                availableTags.value = data.tags;

                // Auto-select first tag
                if (availableTags.value.length > 0 && !selectedTag.value) {
                    selectedTag.value = availableTags.value[0];
                    await fetchCosts();
                } else if (availableTags.value.length === 0) {
                    error.value = 'No tags available. The API returned an empty tag list.';
                }
            } catch (err) {
                console.error('Failed to fetch tags:', err);
                error.value = `Failed to load tags: ${err.message}. You can still manually enter a tag name below.`;
                // Provide common fallback tags
                availableTags.value = ['owner', 'team', 'env', 'app', 'project'];
            }
        }

        async function fetchCosts() {
            if (!selectedTag.value) return;

            loading.value = true;
            error.value = null;

            try {
                // Build query parameters
                const params = new URLSearchParams({
                    tag_key: selectedTag.value,
                    resolution: resolution.value
                });

                // Add time filtering
                if (timePreset.value === 'custom' && startDate.value && endDate.value) {
                    params.append('start_date', startDate.value);
                    params.append('end_date', endDate.value);
                } else {
                    // Use presets
                    const presetMap = {
                        'last-month': { units: 'month', value: -1 },
                        'last-3-days': { units: 'day', value: -3 },
                        'month-to-date': { units: 'month', value: -1 }
                    };

                    const preset = presetMap[timePreset.value];
                    if (preset) {
                        params.append('time_scope_units', preset.units);
                        params.append('time_scope_value', preset.value);
                    }
                }

                const response = await fetch(`${API_BASE}/costs?${params}`);
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.message || `HTTP ${response.status}`);
                }

                costData.value = await response.json();
            } catch (err) {
                console.error('Failed to fetch costs:', err);
                error.value = `Failed to load cost data: ${err.message}`;
            } finally {
                loading.value = false;
            }
        }

        async function showDrillDown(tagValue) {
            showModal.value = true;
            loadingDrillDown.value = true;
            drillDownData.value = null;

            try {
                const params = new URLSearchParams({
                    tag_key: selectedTag.value,
                    tag_value: tagValue,
                    resolution: resolution.value
                });

                // Add same time filtering as main view
                if (timePreset.value === 'custom' && startDate.value && endDate.value) {
                    params.append('start_date', startDate.value);
                    params.append('end_date', endDate.value);
                } else {
                    const presetMap = {
                        'last-month': { units: 'month', value: -1 },
                        'last-3-days': { units: 'day', value: -3 },
                        'month-to-date': { units: 'month', value: -1 }
                    };

                    const preset = presetMap[timePreset.value];
                    if (preset) {
                        params.append('time_scope_units', preset.units);
                        params.append('time_scope_value', preset.value);
                    }
                }

                const response = await fetch(`${API_BASE}/costs/drilldown?${params}`);
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.message || `HTTP ${response.status}`);
                }

                drillDownData.value = await response.json();
            } catch (err) {
                console.error('Failed to fetch drill-down data:', err);
                error.value = `Failed to load project details: ${err.message}`;
                showModal.value = false;
            } finally {
                loadingDrillDown.value = false;
            }
        }

        function closeModal() {
            showModal.value = false;
            drillDownData.value = null;
        }

        // Keyboard shortcuts
        function handleKeydown(event) {
            // ESC to close modal
            if (event.key === 'Escape' && showModal.value) {
                closeModal();
            }
            // R to refresh (when not in input field)
            if (event.key === 'r' && !event.target.matches('input, select, textarea')) {
                event.preventDefault();
                fetchCosts();
            }
        }

        // Event Handlers
        function onTimePresetChange() {
            // Clear custom dates when switching to preset
            if (timePreset.value !== 'custom') {
                startDate.value = '';
                endDate.value = '';
            }
            fetchCosts();
        }

        // Formatters
        function formatCurrency(value) {
            if (value === null || value === undefined) return 'N/A';

            const symbol = currency.value === 'EUR' ? '€' : '$';
            const formatted = new Intl.NumberFormat('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);

            return currency.value === 'EUR'
                ? `${symbol}${formatted}`
                : `${symbol}${formatted}`;
        }

        function formatPercentage(value) {
            if (value === null || value === undefined) return 'N/A';
            return `${(value * 100).toFixed(1)}%`;
        }

        // Lifecycle
        onMounted(async () => {
            initializeTheme();
            await fetchTags();

            // Add keyboard event listener
            window.addEventListener('keydown', handleKeydown);
        });

        // Cleanup on unmount
        const { onUnmounted } = Vue;
        onUnmounted(() => {
            window.removeEventListener('keydown', handleKeydown);
        });

        // Return reactive state and methods
        return {
            // Theme
            selectedTheme,
            changeTheme,

            // Filters
            availableTags,
            selectedTag,
            timePreset,
            resolution,
            startDate,
            endDate,
            currency,

            // Data
            costData,
            drillDownData,

            // UI State
            loading,
            loadingDrillDown,
            error,
            showModal,

            // Methods
            fetchCosts,
            showDrillDown,
            closeModal,
            onTimePresetChange,

            // Formatters
            formatCurrency,
            formatPercentage
        };
    }
}).mount('#app');
