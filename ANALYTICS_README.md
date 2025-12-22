# Dashboard Analytics Feature

## Overview

The Dashboard Analytics feature provides comprehensive insights into certificate generation and download patterns. It enables administrators to monitor usage trends, analyze student behavior, and generate reports.

## Features

### 1. **Core Metrics**
- **Total Downloads**: Complete count of all certificate downloads
- **Unique Students**: Number of distinct students who downloaded certificates
- **Peak Hour**: Hour of the day with maximum downloads

### 2. **Visual Analytics**
- **Certificate Type Distribution**: Doughnut chart showing download breakdown by certificate type
- **Top 5 Students**: Horizontal bar chart of students with most downloads
- **Daily Trend (30 days)**: Line chart showing download patterns over the last month
- **Hourly Distribution**: Bar chart showing downloads by hour of day
- **Monthly Comparison**: Line chart comparing last 6 months of activity

### 3. **Advanced Metrics**
- **Average Downloads per Student**: Mean downloads per unique student
- **Most Popular Certificate**: Most downloaded certificate type

### 4. **Filtering & Export**
- **Date Range Filter**: Analyze data for specific date ranges
- **CSV Export**: Download all analytics data in CSV format
- **Quick Reset**: Reset filters to view all-time data

## API Endpoints

### Get Basic Analytics
```
GET /admin/api/analytics
```
**Response:**
```json
{
  "total_downloads": 150,
  "unique_students": 45,
  "cert_type_data": {
    "Bonafide": 60,
    "Course Completion": 30,
    "Custodium": 25,
    "Fee details for IT purpose": 20,
    "Fee structure for bank loan": 15
  },
  "daily_data": {
    "2024-12-15": 10,
    "2024-12-16": 15,
    "2024-12-17": 8
  },
  "peak_hour": "14:00",
  "top_students": {
    "CS001": 5,
    "CS002": 4,
    "CS003": 3
  }
}
```

### Get Advanced Analytics
```
GET /admin/api/analytics/advanced
```
**Response:**
```json
{
  "hourly_distribution": {
    "00:00": 2,
    "01:00": 1,
    "14:00": 25,
    "15:00": 20
  },
  "monthly_comparison": {
    "July 2024": 120,
    "August 2024": 135,
    "September 2024": 150
  },
  "success_metrics": {
    "total_requests": 150,
    "most_popular_cert": "Bonafide",
    "most_popular_count": 60,
    "avg_per_student": 3.33
  }
}
```

### Get Date Range Analytics
```
POST /admin/api/analytics/date-range
Content-Type: application/json

{
  "start_date": "2024-12-01",
  "end_date": "2024-12-31"
}
```
**Response:**
```json
{
  "total_downloads": 85,
  "unique_students": 30,
  "cert_type_distribution": {
    "Bonafide": 35,
    "Course Completion": 20,
    "Custodium": 15,
    "Fee details for IT purpose": 10,
    "Fee structure for bank loan": 5
  },
  "date_range": {
    "start": "2024-12-01",
    "end": "2024-12-31"
  }
}
```

### Export Analytics Data
```
GET /admin/api/analytics/export/csv
```
Downloads a CSV file containing all certificate download records with columns:
- Hall Ticket
- Certificate Type
- Transaction ID
- Downloaded At

## AnalyticsService Class

The `AnalyticsService` class provides methods for analytics data aggregation:

### Methods

#### `get_total_downloads()`
Returns total number of certificate downloads.

#### `get_unique_students()`
Returns count of unique students.

#### `get_certificate_type_distribution()`
Returns dictionary with certificate types and their counts.

#### `get_daily_downloads(days=30)`
Returns daily download counts for the specified number of days.

#### `get_hourly_distribution()`
Returns downloads grouped by hour of day.

#### `get_peak_hour()`
Returns the hour with maximum downloads.

#### `get_top_students(limit=5)`
Returns top N students by download count.

#### `get_analytics_by_date_range(start_date, end_date)`
Returns analytics for a specific date range (YYYY-MM-DD format).

#### `get_monthly_comparison(months=6)`
Returns month-wise comparison for the last N months.

#### `export_data_csv()`
Generates CSV string of all certificate downloads.

## Usage Guide

### Accessing the Analytics Dashboard

1. Log in to the admin panel (`/admin`)
2. Click the "📊 Analytics" tab in the dashboard
3. View real-time metrics and charts

### Filtering by Date Range

1. Select start date using the "Start Date" input
2. Select end date using the "End Date" input
3. Click "📅 Filter" button
4. Results show analytics for the selected period
5. Click "Reset" to view all-time data

### Exporting Data

1. Navigate to the Analytics tab
2. Click "⬇️ Export CSV" button
3. The CSV file will be downloaded automatically

## Implementation Details

### Database Model
The analytics feature uses the `CertificateDownload` model:
```python
class CertificateDownload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_hallticket = db.Column(db.String(50), nullable=False)
    certificate_type = db.Column(db.String(100), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)
    proof_filename = db.Column(db.String(200), nullable=True)
    downloaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
```

### Frontend Libraries
- **Chart.js 3.9.1**: For interactive visualizations
- **Vanilla JavaScript**: For dynamic updates and filtering

### Chart Types Used
- **Doughnut Chart**: Certificate type distribution
- **Horizontal Bar Chart**: Top students
- **Line Chart**: Daily trends and monthly comparison
- **Bar Chart**: Hourly distribution

## Performance Considerations

- Analytics queries are optimized using SQLAlchemy aggregation functions
- Daily data is limited to last 30 days for better performance
- Charts are destroyed and recreated to prevent memory leaks
- Advanced metrics load asynchronously to prevent UI blocking

## Security

- All analytics endpoints require admin authentication
- Session-based access control on all API endpoints
- Data export includes only aggregate information

## Future Enhancements

- Student status distribution chart
- Custom date range selection in filters
- Email report generation
- Real-time notifications for milestones
- Role-based analytics access
- Performance metrics by certificate type

## Troubleshooting

### Analytics not loading
- Check browser console for JavaScript errors
- Verify admin session is active
- Ensure database contains certificate download records

### Charts not displaying
- Clear browser cache
- Check if Chart.js CDN is accessible
- Verify JavaScript is enabled

### Export not working
- Ensure browser allows file downloads
- Check admin permissions
- Verify database connectivity

## Support

For issues or feature requests related to analytics, please refer to the main project documentation or create an issue in the repository.
