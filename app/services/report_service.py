import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.db.models.merchant import MerchantFavorite, MerchantProfile
from app.db.models.product import ProductOrder
from app.db.models.promotion import Promotion
from app.db.models.search_event import SearchEvent
from app.db.models.subscription import UserSubscription, UserSubscriptionStatus
from app.db.models.user import User, UserRole
from app.schemas.report import (
    AdminReportsResponse,
    DistrictReportItem,
    EngagementReport,
    LeadsReport,
    MerchantAdditionsCard,
    MonthlyTrendPoint,
    ReportCards,
    SectorReportItem,
    VerificationCard,
)

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class ReportService:
    @staticmethod
    def resolve_range(
        year: Optional[int],
        date_from: Optional[date],
        date_to: Optional[date],
        all_years: bool,
    ) -> Tuple[Optional[datetime], Optional[datetime], Optional[int], bool]:
        if all_years:
            return None, None, None, True
        if date_from or date_to:
            start_date = date_from or date(1970, 1, 1)
            end_date = date_to or date.today()
            start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
            report_year = year or start_date.year
            return start, end, report_year, False
        report_year = year or datetime.now(timezone.utc).year
        start = datetime(report_year, 1, 1, tzinfo=timezone.utc)
        end = datetime(report_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        return start, end, report_year, False

    @staticmethod
    def build_reports(
        db: Session,
        year: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        all_years: bool = False,
        sector: Optional[str] = None,
    ) -> AdminReportsResponse:
        start, end, report_year, all_years_flag = ReportService.resolve_range(
            year, date_from, date_to, all_years
        )
        merchants = ReportService._merchants_in_range(db, start, end)
        paid_ids = ReportService._paid_merchant_ids(db)
        additions, trend = ReportService._merchant_growth(merchants, paid_ids, report_year, all_years_flag)
        directory = ReportService._directory_merchants(db)
        districts = ReportService._districts(directory)
        sectors = ReportService._sectors(directory, sector)
        verification = ReportService._verification(directory)
        engagement = ReportService._engagement(db, start, end)
        leads = ReportService._leads(db, start, end, directory)
        return AdminReportsResponse(
            year=report_year,
            all_years=all_years_flag,
            date_from=start.date() if start else None,
            date_to=end.date() if end else None,
            cards=ReportCards(
                merchant_additions=additions,
                active_customers=engagement.active_customers,
                customer_leads_and_calls=leads.customer_leads_and_calls,
                verification=verification,
            ),
            monthly_trend=trend,
            districts=districts,
            sectors=sectors,
            sector_count=len(sectors),
            engagement=engagement,
            leads=leads,
        )

    @staticmethod
    def to_csv(report: AdminReportsResponse) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        cards = report.cards
        writer.writerow(["section", "metric", "value"])
        writer.writerow(["cards", "merchant_additions", cards.merchant_additions.total])
        writer.writerow(["cards", "paid", cards.merchant_additions.paid])
        writer.writerow(["cards", "free", cards.merchant_additions.free])
        writer.writerow(["cards", "active_customers", cards.active_customers])
        writer.writerow(["cards", "customer_leads_and_calls", cards.customer_leads_and_calls])
        writer.writerow(["cards", "verification_rate_percent", cards.verification.rate_percent])
        writer.writerow([])
        writer.writerow(["month", "paid", "free", "total", "cumulative"])
        for point in report.monthly_trend:
            writer.writerow([point.label, point.paid, point.free, point.total, point.cumulative])
        writer.writerow([])
        writer.writerow(["district", "merchants", "percent"])
        for row in report.districts:
            writer.writerow([row.district, row.merchants, row.percent])
        writer.writerow([])
        writer.writerow(["sector", "shops", "percent"])
        for row in report.sectors:
            writer.writerow([row.sector, row.shops, row.percent])
        return buffer.getvalue()

    @staticmethod
    def _merchants_in_range(db: Session, start: Optional[datetime], end: Optional[datetime]) -> List[MerchantProfile]:
        query = db.query(MerchantProfile)
        if start is not None:
            query = query.filter(MerchantProfile.created_at >= start)
        if end is not None:
            query = query.filter(MerchantProfile.created_at <= end)
        return query.all()

    @staticmethod
    def _directory_merchants(db: Session) -> List[MerchantProfile]:
        return db.query(MerchantProfile).all()

    @staticmethod
    def _paid_merchant_ids(db: Session) -> set:
        paid = set()
        rows = (
            db.query(UserSubscription.merchant_profile_id, UserSubscription.amount_paid, UserSubscription.status)
            .filter(UserSubscription.status != UserSubscriptionStatus.CANCELLED)
            .all()
        )
        for profile_id, amount_paid, status in rows:
            if profile_id is None:
                continue
            amount = Decimal(str(amount_paid or 0))
            if status == UserSubscriptionStatus.ACTIVE or amount > 0:
                paid.add(profile_id)
        flagged = (
            db.query(MerchantProfile.id)
            .filter(MerchantProfile.has_active_subscription.is_(True))
            .all()
        )
        paid.update(row[0] for row in flagged)
        return paid

    @staticmethod
    def _merchant_growth(merchants, paid_ids, report_year, all_years):
        paid = free = 0
        buckets = {month: {"paid": 0, "free": 0} for month in range(1, 13)}
        for merchant in merchants:
            created = merchant.created_at
            if created is None:
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if not all_years and report_year and created.year != report_year:
                continue
            is_paid = merchant.id in paid_ids
            if is_paid:
                paid += 1
            else:
                free += 1
            buckets[created.month]["paid" if is_paid else "free"] += 1
        total = paid + free
        additions = MerchantAdditionsCard(
            total=total,
            paid=paid,
            free=free,
            paid_percent=ReportService._percent(paid, total),
            free_percent=ReportService._percent(free, total),
        )
        trend = []
        cumulative = 0
        for month in range(1, 13):
            month_paid = buckets[month]["paid"]
            month_free = buckets[month]["free"]
            month_total = month_paid + month_free
            cumulative += month_total
            trend.append(
                MonthlyTrendPoint(
                    month=month,
                    label=MONTH_LABELS[month - 1],
                    paid=month_paid,
                    free=month_free,
                    total=month_total,
                    cumulative=cumulative,
                )
            )
        return additions, trend

    @staticmethod
    def _districts(merchants: List[MerchantProfile]) -> List[DistrictReportItem]:
        counts = {}
        for merchant in merchants:
            name = (merchant.district or "Unknown").strip() or "Unknown"
            counts[name] = counts.get(name, 0) + 1
        total = sum(counts.values())
        rows = [
            DistrictReportItem(
                district=name,
                merchants=count,
                percent=ReportService._percent(count, total),
            )
            for name, count in counts.items()
        ]
        rows.sort(key=lambda item: (-item.merchants, item.district))
        return rows

    @staticmethod
    def _sectors(merchants: List[MerchantProfile], sector: Optional[str]) -> List[SectorReportItem]:
        counts = {}
        needle = sector.strip().lower() if sector else None
        for merchant in merchants:
            name = (merchant.category or "Uncategorized").strip() or "Uncategorized"
            if needle and needle not in name.lower():
                continue
            counts[name] = counts.get(name, 0) + 1
        total = sum(counts.values())
        rows = [
            SectorReportItem(
                sector=name,
                shops=count,
                percent=ReportService._percent(count, total),
            )
            for name, count in counts.items()
        ]
        rows.sort(key=lambda item: (-item.shops, item.sector))
        return rows

    @staticmethod
    def _verification(merchants: List[MerchantProfile]) -> VerificationCard:
        approved = pending = rejected = 0
        for merchant in merchants:
            status = (merchant.approval_status or merchant.status or "").strip().upper()
            if status in {"APPROVED", "VERIFIED"} or merchant.is_verified:
                approved += 1
            elif status == "REJECTED":
                rejected += 1
            else:
                pending += 1
        total = approved + pending + rejected
        return VerificationCard(
            approved=approved,
            pending=pending,
            rejected=rejected,
            total=total,
            rate_percent=ReportService._percent(approved, total),
            label="Approved",
        )

    @staticmethod
    def _customer_query(db: Session):
        merchant_user_ids = db.query(MerchantProfile.user_id)
        empty_access = or_(
            User.module_access.is_(None),
            cast(User.module_access, String).in_(("[]", "null", "")),
        )
        return db.query(User).filter(
            User.role == UserRole.FIELD_STAFF,
            User.is_active.is_(True),
            ~User.id.in_(merchant_user_ids),
            empty_access,
        )

    @staticmethod
    def _engagement(db: Session, start: Optional[datetime], end: Optional[datetime]) -> EngagementReport:
        customers = ReportService._customer_query(db)
        active_customers = customers.count()
        added = customers
        if start is not None:
            added = added.filter(User.created_at >= start)
        if end is not None:
            added = added.filter(User.created_at <= end)
        districts = (
            customers.filter(User.district.isnot(None), User.district != "")
            .with_entities(func.count(func.distinct(User.district)))
            .scalar()
            or 0
        )
        search_query = db.query(func.count(SearchEvent.id))
        favorite_query = db.query(func.count(MerchantFavorite.id))
        if start is not None:
            search_query = search_query.filter(SearchEvent.created_at >= start)
            favorite_query = favorite_query.filter(MerchantFavorite.created_at >= start)
        if end is not None:
            search_query = search_query.filter(SearchEvent.created_at <= end)
            favorite_query = favorite_query.filter(MerchantFavorite.created_at <= end)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        recently_active = customers.filter(User.last_active.isnot(None), User.last_active >= recent_cutoff).count()
        return EngagementReport(
            active_customers=active_customers,
            customers_added=added.count(),
            districts_reached=int(districts),
            searches=int(search_query.scalar() or 0),
            favorites=int(favorite_query.scalar() or 0),
            recently_active=recently_active,
        )

    @staticmethod
    def _leads(
        db: Session,
        start: Optional[datetime],
        end: Optional[datetime],
        directory: List[MerchantProfile],
    ) -> LeadsReport:
        clicks_query = db.query(func.coalesce(func.sum(Promotion.clicks), 0))
        impressions_query = db.query(func.coalesce(func.sum(Promotion.impressions), 0))
        orders_query = db.query(func.count(ProductOrder.id))
        search_query = db.query(func.count(SearchEvent.id))
        if start is not None:
            clicks_query = clicks_query.filter(Promotion.created_at >= start)
            impressions_query = impressions_query.filter(Promotion.created_at >= start)
            orders_query = orders_query.filter(ProductOrder.created_at >= start)
            search_query = search_query.filter(SearchEvent.created_at >= start)
        if end is not None:
            clicks_query = clicks_query.filter(Promotion.created_at <= end)
            impressions_query = impressions_query.filter(Promotion.created_at <= end)
            orders_query = orders_query.filter(ProductOrder.created_at <= end)
            search_query = search_query.filter(SearchEvent.created_at <= end)
        clicks = int(clicks_query.scalar() or 0)
        impressions = int(impressions_query.scalar() or 0)
        orders = int(orders_query.scalar() or 0)
        searches = int(search_query.scalar() or 0)
        whatsapp_merchants = sum(1 for merchant in directory if (merchant.whatsapp or "").strip())
        zero_commission = sum(
            1 for merchant in directory if Decimal(str(merchant.company_fee_percent or 0)) == 0
        )
        return LeadsReport(
            customer_leads_and_calls=searches + clicks + orders,
            searches=searches,
            promotion_clicks=clicks,
            promotion_impressions=impressions,
            product_orders=orders,
            whatsapp_merchants=whatsapp_merchants,
            zero_commission_deals=zero_commission,
        )

    @staticmethod
    def _percent(part: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round((part / total) * 100, 1)
