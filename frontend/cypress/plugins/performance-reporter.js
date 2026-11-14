const fs = require('fs');
const path = require('path');

const performanceMetrics = {
  tests: {},
  summary: {
    totalTests: 0,
    averageDuration: 0,
    slowestTest: { name: '', duration: 0 },
    fastestTest: { name: '', duration: Infinity }
  }
};

function calculateSummary() {
  const tests = Object.values(performanceMetrics.tests);
  performanceMetrics.summary.totalTests = tests.length;
  
  if (tests.length > 0) {
    const validTests = tests.filter(test => test.duration > 0);
    if (validTests.length > 0) {
      const totalDuration = validTests.reduce((sum, test) => sum + test.duration, 0);
      performanceMetrics.summary.averageDuration = totalDuration / validTests.length;
      
      validTests.forEach(test => {
        if (test.duration > performanceMetrics.summary.slowestTest.duration) {
          performanceMetrics.summary.slowestTest = { name: test.name, duration: test.duration };
        }
        if (test.duration < performanceMetrics.summary.fastestTest.duration) {
          performanceMetrics.summary.fastestTest = { name: test.name, duration: test.duration };
        }
      });
    }
  }
}

function generateHTMLReport() {
  const tests = Object.values(performanceMetrics.tests);
  const testNames = tests.map(test => test.name);
  const durations = tests.map(test => test.duration || 0);

  const htmlContent = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cypress Performance Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .summary-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background-color: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card h3 {
            margin-top: 0;
            color: #333;
        }
        .card p {
            font-size: 24px;
            font-weight: bold;
            color: #2196F3;
            margin: 10px 0;
        }
        .chart-container {
            margin-top: 30px;
            height: 400px;
        }
        .test-list {
            margin-top: 30px;
        }
        .test-list table {
            width: 100%;
            border-collapse: collapse;
        }
        .test-list th, .test-list td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .test-list th {
            background-color: #f8f9fa;
        }
        .test-list tr:hover {
            background-color: #f5f5f5;
        }
        .timestamp {
            color: #666;
            font-size: 0.9em;
            text-align: right;
            margin-top: 20px;
        }
        .status-passed {
            color: #4CAF50;
        }
        .status-failed {
            color: #F44336;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Cypress Performance Report</h1>
            <p class="timestamp">Generated on: ${new Date().toLocaleString()}</p>
        </div>
        
        <div class="summary-cards">
            <div class="card">
                <h3>Total Tests</h3>
                <p>${performanceMetrics.summary.totalTests}</p>
            </div>
            <div class="card">
                <h3>Average Duration</h3>
                <p>${performanceMetrics.summary.averageDuration.toFixed(2)}ms</p>
            </div>
            <div class="card">
                <h3>Slowest Test</h3>
                <p>${performanceMetrics.summary.slowestTest.duration.toFixed(2)}ms</p>
                <small>${performanceMetrics.summary.slowestTest.name}</small>
            </div>
            <div class="card">
                <h3>Fastest Test</h3>
                <p>${performanceMetrics.summary.fastestTest.duration.toFixed(2)}ms</p>
                <small>${performanceMetrics.summary.fastestTest.name}</small>
            </div>
        </div>

        <div class="chart-container">
            <canvas id="testDurationChart"></canvas>
        </div>

        <div class="test-list">
            <h2>Detailed Test Results</h2>
            <table>
                <thead>
                    <tr>
                        <th>Test Name</th>
                        <th>Duration (ms)</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${tests.map(test => `
                        <tr>
                            <td>${test.name}</td>
                            <td>${(test.duration || 0).toFixed(2)}</td>
                            <td class="status-${test.state.toLowerCase()}">${test.state}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const ctx = document.getElementById('testDurationChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ${JSON.stringify(testNames)},
                datasets: [{
                    label: 'Test Duration (ms)',
                    data: ${JSON.stringify(durations)},
                    backgroundColor: 'rgba(33, 150, 243, 0.5)',
                    borderColor: 'rgba(33, 150, 243, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Duration (ms)'
                        }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    </script>
</body>
</html>
  `;

  const reportDir = path.join(__dirname, '../../docs/performance');
  if (!fs.existsSync(reportDir)) {
    fs.mkdirSync(reportDir, { recursive: true });
  }
  const reportPath = path.join(reportDir, 'performance-report.html');
  fs.writeFileSync(reportPath, htmlContent);
  
  console.log('\nPerformance Report:');
  console.log('------------------');
  console.log(`Total Tests: ${performanceMetrics.summary.totalTests}`);
  console.log(`Average Duration: ${performanceMetrics.summary.averageDuration.toFixed(2)}ms`);
  console.log(`Slowest Test: ${performanceMetrics.summary.slowestTest.name} (${performanceMetrics.summary.slowestTest.duration.toFixed(2)}ms)`);
  console.log(`Fastest Test: ${performanceMetrics.summary.fastestTest.name} (${performanceMetrics.summary.fastestTest.duration.toFixed(2)}ms)`);
  console.log(`\nHTML report generated at: ${reportPath}`);
}

module.exports = (on, config) => {
  on('before:run', () => {
    performanceMetrics.tests = {};
    performanceMetrics.summary = {
      totalTests: 0,
      averageDuration: 0,
      slowestTest: { name: '', duration: 0 },
      fastestTest: { name: '', duration: Infinity }
    };
  });

  on('after:spec', (spec, results) => {
    if (results && results.tests) {
      results.tests.forEach(test => {
        const testName = test.title.join(' > ');
        const duration = test.attempts && test.attempts[0] ? test.attempts[0].duration : 0;
        performanceMetrics.tests[testName] = {
          name: testName,
          duration: duration,
          state: test.state
        };
      });
    }
  });

  on('after:run', () => {
    calculateSummary();
    generateHTMLReport();
  });
}; 