"""
Analytics Service Module
Provides analytics functionality for the Certificate Generator application.
Handles data aggregation, trend analysis, and reporting.
"""

from datetime import datetime, timedelta
from sqlalchemy import func
from flask import current_app
from collections import defaultdict


class AnalyticsService:
    """Service class for handling analytics queries and computations."""
    
    def __init__(self, db, CertificateDownload):
        """Initialize analytics service with database models."""
        self.db = db
        self.CertificateDownload = CertificateDownload
    
    def get_total_downloads(self):
        """Get total number of certificate downloads."""
        return self.CertificateDownload.query.count()
    
    def get_unique_students(self):
        """Get count of unique students who downloaded certificates."""
        return self.db.session.query(
            func.count(func.distinct(self.CertificateDownload.student_hallticket))
        ).scalar() or 0
    
    def get_certificate_type_distribution(self):
        """Get distribution of downloads by certificate type."""
        cert_type_counts = self.db.session.query(
            self.CertificateDownload.certificate_type,
            func.count(self.CertificateDownload.id).label("count")
        ).group_by(self.CertificateDownload.certificate_type).all()
        
        return {cert_type: count for cert_type, count in cert_type_counts}
    
    def get_daily_downloads(self, days=30):
        """Get daily download counts for the last N days."""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        daily_downloads = self.db.session.query(
            func.date(self.CertificateDownload.downloaded_at).label("date"),
            func.count(self.CertificateDownload.id).label("count")
        ).filter(
            self.CertificateDownload.downloaded_at >= start_date
        ).group_by(
            func.date(self.CertificateDownload.downloaded_at)
        ).order_by("date").all()
        
        return {str(date): count for date, count in daily_downloads}
    
    def get_hourly_distribution(self):
        """Get distribution of downloads by hour of day."""
        hourly_data = self.db.session.query(
            func.strftime('%H', self.CertificateDownload.downloaded_at).label("hour"),
            func.count(self.CertificateDownload.id).label("count")
        ).group_by(
            func.strftime('%H', self.CertificateDownload.downloaded_at)
        ).order_by("hour").all()
        
        return {f"{hour}:00": count for hour, count in hourly_data}
    
    def get_peak_hour(self):
        """Get the hour with most downloads."""
        peak_hour_data = self.db.session.query(
            func.strftime('%H', self.CertificateDownload.downloaded_at).label("hour"),
            func.count(self.CertificateDownload.id).label("count")
        ).group_by(
            func.strftime('%H', self.CertificateDownload.downloaded_at)
        ).order_by(
            func.count(self.CertificateDownload.id).desc()
        ).first()
        
        return peak_hour_data[0] + ":00" if peak_hour_data else "N/A"
    
    def get_top_students(self, limit=5):
        """Get top N students by download count."""
        top_students = self.db.session.query(
            self.CertificateDownload.student_hallticket,
            func.count(self.CertificateDownload.id).label("count")
        ).group_by(
            self.CertificateDownload.student_hallticket
        ).order_by(
            func.count(self.CertificateDownload.id).desc()
        ).limit(limit).all()
        
        return {student: count for student, count in top_students}
    
    def get_analytics_by_date_range(self, start_date, end_date):
        """Get analytics for a specific date range."""
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        
        downloads = self.CertificateDownload.query.filter(
            self.CertificateDownload.downloaded_at >= start_dt,
            self.CertificateDownload.downloaded_at < end_dt
        ).all()
        
        total = len(downloads)
        unique_students = len(set(d.student_hallticket for d in downloads))
        
        cert_type_dist = defaultdict(int)
        for d in downloads:
            cert_type_dist[d.certificate_type] += 1
        
        return {
            "total_downloads": total,
            "unique_students": unique_students,
            "cert_type_distribution": dict(cert_type_dist),
            "date_range": {"start": start_date, "end": end_date}
        }
    
    def get_monthly_comparison(self, months=6):
        """Get month-wise download comparison for the last N months."""
        monthly_data = {}
        
        for i in range(months):
            month_start = datetime.utcnow().replace(day=1) - timedelta(days=30*i)
            month_start = month_start.replace(day=1)
            
            if i == 0:
                month_end = datetime.utcnow()
            else:
                month_end = month_start + timedelta(days=30)
            
            month_key = month_start.strftime("%B %Y")
            
            count = self.CertificateDownload.query.filter(
                self.CertificateDownload.downloaded_at >= month_start,
                self.CertificateDownload.downloaded_at <= month_end
            ).count()
            
            monthly_data[month_key] = count
        
        return dict(reversed(list(monthly_data.items())))
    
    def get_student_status_distribution(self, students_df):
        """Get distribution of downloads by student status."""
        status_dist = defaultdict(int)
        
        downloads = self.CertificateDownload.query.all()
        
        for download in downloads:
            student = students_df[students_df["HALLTICKET"] == download.student_hallticket]
            if not student.empty:
                status = str(student["STATUS"].values[0]).strip().upper()
                status_dist[status] += 1
        
        return dict(status_dist)
    
    def get_certificate_success_rate(self):
        """Get information about certificate generation patterns."""
        total_requests = self.CertificateDownload.query.count()
        
        cert_distribution = self.get_certificate_type_distribution()
        most_popular = max(cert_distribution.items(), key=lambda x: x[1], default=("N/A", 0))
        
        return {
            "total_requests": total_requests,
            "most_popular_cert": most_popular[0],
            "most_popular_count": most_popular[1],
            "avg_per_student": round(
                total_requests / max(self.get_unique_students(), 1), 2
            )
        }
    
    def export_data_csv(self):
        """Generate CSV export of all certificate downloads."""
        downloads = self.CertificateDownload.query.all()
        
        csv_lines = ["Hall Ticket,Certificate Type,Transaction ID,Downloaded At"]
        for download in downloads:
            csv_lines.append(
                f"{download.student_hallticket},"
                f"{download.certificate_type},"
                f"{download.transaction_id or 'N/A'},"
                f"{download.downloaded_at.strftime('%d-%m-%Y %H:%M:%S')}"
            )
        
        return "\n".join(csv_lines)


def create_analytics_service(db, CertificateDownload):
    """Factory function to create analytics service."""
    return AnalyticsService(db, CertificateDownload)
