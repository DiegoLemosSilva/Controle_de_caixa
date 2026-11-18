/* Visualização dos dados calculados no servidor; a tabela mantém os valores exatos. */
(() => {
    const dataElement = document.getElementById('annual-charts-data');
    if (!dataElement || !window.echarts) return;

    let charts;
    try {
        charts = JSON.parse(dataElement.textContent);
    } catch (error) {
        console.error('Não foi possível carregar os dados dos gráficos anuais.', error);
        return;
    }

    const currency = new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
    });
    const colors = ['#176b86', '#a85a08'];

    document.querySelectorAll('[data-annual-chart]').forEach((element) => {
        const chartData = charts[Number(element.dataset.annualChart)];
        if (!chartData || !Array.isArray(chartData.rows)) return;

        const fallback = element.parentElement.querySelector('.annual-chart__graphic');
        const horizontal = element.dataset.orientation === 'horizontal';
        const showBarValues = element.dataset.barValueLabels === 'true';
        const hasNegativeValues = chartData.rows.some((row) => (
            row.bars.some((bar) => !bar.pending && Number(bar.value) < 0)
        ));
        const categoryAxis = {
            type: 'category',
            inverse: horizontal,
            data: chartData.rows.map((row) => row.short_name),
            axisLabel: {
                interval: 0,
                color: '#354b45',
                margin: hasNegativeValues ? (horizontal ? 130 : 100) : 8,
            },
            axisTick: { alignWithLabel: true },
        };
        const valueAxis = {
            type: 'value',
            axisLabel: {
                show: !showBarValues,
                color: '#354b45',
                formatter: (value) => currency.format(value),
            },
            splitLine: { lineStyle: { color: '#e6eeea' } },
        };
        let instance;
        try {
            element.hidden = false;
            instance = window.echarts.init(element);
            instance.setOption({
                color: colors,
                animation: false,
                grid: {
                    left: showBarValues ? 8 : (horizontal ? 80 : 12),
                    right: horizontal ? 145 : 24,
                    top: horizontal ? 20 : 110,
                    bottom: horizontal ? 42 : 30,
                    containLabel: true,
                },
                tooltip: {
                    trigger: 'axis',
                    renderMode: 'richText',
                    axisPointer: { type: 'shadow' },
                    formatter: (params) => {
                        const row = chartData.rows[params[0].dataIndex];
                        const lines = [row.name + ' — ' + row.status];
                        row.bars.forEach((bar) => {
                            lines.push(bar.label + ': ' + (bar.pending
                                ? 'Pendente'
                                : currency.format(Number(bar.value))));
                        });
                        return lines.join('\n');
                    },
                },
                xAxis: horizontal ? valueAxis : categoryAxis,
                yAxis: horizontal ? categoryAxis : valueAxis,
                series: [0, 1].map((index) => ({
                    name: index === 0 ? chartData.label_a : chartData.label_b,
                    type: 'bar',
                    barMaxWidth: 22,
                    label: {
                        show: true,
                        position: 'outside',
                        rotate: horizontal ? 0 : 90,
                        color: '#354b45',
                        fontSize: 11,
                        formatter: (params) => currency.format(params.value),
                    },
                    data: chartData.rows.map((row) => {
                        const bar = row.bars[index];
                        if (bar.pending) return null;
                        const value = Number(bar.value);
                        if (horizontal) return value;
                        return {
                            value,
                            label: {
                                position: value < 0 ? 'bottom' : 'top',
                                align: value < 0 ? 'right' : 'left',
                                verticalAlign: 'middle',
                            },
                        };
                    }),
                })),
            });
            if (fallback) fallback.setAttribute('hidden', '');
            if (window.ResizeObserver) {
                const observer = new ResizeObserver(() => instance.resize());
                observer.observe(element);
            } else {
                window.addEventListener('resize', () => instance.resize());
            }
        } catch (error) {
            if (instance) instance.dispose();
            element.hidden = true;
            if (fallback) fallback.removeAttribute('hidden');
            console.error('Não foi possível exibir um gráfico anual.', error);
        }
    });
})();
