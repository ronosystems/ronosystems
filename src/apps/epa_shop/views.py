from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from datetime import timedelta
from django.contrib.contenttypes.models import ContentType

from .models import (
    Category, Electronic, Phone, Accessory, 
    Sale, SaleItem, Customer, Branch, Supplier,
    StockMovement, PurchaseOrder, PurchaseOrderItem,
    Warranty, Repair
)
from .serializers import (
    CategorySerializer, ElectronicSerializer, PhoneSerializer,
    AccessorySerializer, SaleSerializer, SaleCreateSerializer,
    SaleItemSerializer, CustomerSerializer, BranchSerializer,
    BranchDetailSerializer, SupplierSerializer, StockMovementSerializer,
    StockMovementCreateSerializer, PurchaseOrderSerializer,
    PurchaseOrderItemSerializer, WarrantySerializer, RepairSerializer
)
from apps.accounts.permissions import IsCompanyAdmin

# ============================================
# BRANCH VIEWS
# ============================================

class BranchListCreateView(generics.ListCreateAPIView):
    """List and create branches"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return BranchDetailSerializer
        return BranchSerializer
    
    def get_queryset(self):
        return Branch.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class BranchDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, delete branch"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = BranchSerializer
    
    def get_queryset(self):
        return Branch.objects.filter(company=self.request.user.company)

# ============================================
# SUPPLIER VIEWS
# ============================================

class SupplierListCreateView(generics.ListCreateAPIView):
    """List and create suppliers"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = SupplierSerializer
    
    def get_queryset(self):
        return Supplier.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, delete supplier"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = SupplierSerializer
    
    def get_queryset(self):
        return Supplier.objects.filter(company=self.request.user.company)

# ============================================
# CATEGORY VIEWS
# ============================================

class CategoryListCreateView(generics.ListCreateAPIView):
    """List and create categories"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        return Category.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, delete category"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        return Category.objects.filter(company=self.request.user.company)

# ============================================
# ELECTRONIC VIEWS
# ============================================

class ElectronicListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = ElectronicSerializer
    
    def get_queryset(self):
        queryset = Electronic.objects.filter(company=self.request.user.company)
        branch = self.request.query_params.get('branch')
        category = self.request.query_params.get('category')
        search = self.request.query_params.get('search')
        
        if branch:
            queryset = queryset.filter(branch_id=branch)
        if category:
            queryset = queryset.filter(category_id=category)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(brand__icontains=search) | 
                Q(serial_number__icontains=search)
            )
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class ElectronicDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = ElectronicSerializer
    
    def get_queryset(self):
        return Electronic.objects.filter(company=self.request.user.company)

# ============================================
# PHONE VIEWS
# ============================================

class PhoneListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = PhoneSerializer
    
    def get_queryset(self):
        queryset = Phone.objects.filter(company=self.request.user.company)
        branch = self.request.query_params.get('branch')
        condition = self.request.query_params.get('condition')
        search = self.request.query_params.get('search')
        
        if branch:
            queryset = queryset.filter(branch_id=branch)
        if condition:
            queryset = queryset.filter(condition=condition)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(brand__icontains=search) | 
                Q(imei__icontains=search)
            )
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class PhoneDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = PhoneSerializer
    
    def get_queryset(self):
        return Phone.objects.filter(company=self.request.user.company)

# ============================================
# ACCESSORY VIEWS
# ============================================

class AccessoryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = AccessorySerializer
    
    def get_queryset(self):
        queryset = Accessory.objects.filter(company=self.request.user.company)
        branch = self.request.query_params.get('branch')
        accessory_type = self.request.query_params.get('accessory_type')
        search = self.request.query_params.get('search')
        
        if branch:
            queryset = queryset.filter(branch_id=branch)
        if accessory_type:
            queryset = queryset.filter(accessory_type=accessory_type)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(brand__icontains=search)
            )
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class AccessoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = AccessorySerializer
    
    def get_queryset(self):
        return Accessory.objects.filter(company=self.request.user.company)

# ============================================
# SALE VIEWS
# ============================================

class SaleListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return SaleCreateSerializer
        return SaleSerializer
    
    def get_queryset(self):
        queryset = Sale.objects.filter(company=self.request.user.company)
        branch = self.request.query_params.get('branch')
        status = self.request.query_params.get('status')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if branch:
            queryset = queryset.filter(branch_id=branch)
        if status:
            queryset = queryset.filter(payment_status=status)
        if date_from:
            queryset = queryset.filter(sale_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(sale_date__date__lte=date_to)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, sold_by=self.request.user)

class SaleDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = SaleSerializer
    
    def get_queryset(self):
        return Sale.objects.filter(company=self.request.user.company)

class SaleInvoiceView(APIView):
    """Get sale invoice details"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get(self, request, pk):
        try:
            sale = Sale.objects.get(id=pk, company=request.user.company)
            serializer = SaleSerializer(sale)
            return Response(serializer.data)
        except Sale.DoesNotExist:
            return Response(
                {'error': 'Sale not found'},
                status=status.HTTP_404_NOT_FOUND
            )

# ============================================
# CUSTOMER VIEWS
# ============================================

class CustomerListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = CustomerSerializer
    
    def get_queryset(self):
        queryset = Customer.objects.filter(company=self.request.user.company)
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(phone__icontains=search) | 
                Q(email__icontains=search)
            )
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = CustomerSerializer
    
    def get_queryset(self):
        return Customer.objects.filter(company=self.request.user.company)

# ============================================
# STOCK MOVEMENT VIEWS
# ============================================

class StockMovementListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return StockMovementCreateSerializer
        return StockMovementSerializer
    
    def get_queryset(self):
        queryset = StockMovement.objects.filter(company=self.request.user.company)
        branch = self.request.query_params.get('branch')
        movement_type = self.request.query_params.get('type')
        
        if branch:
            queryset = queryset.filter(branch_id=branch)
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        serializer.save(
            company=self.request.user.company,
            performed_by=self.request.user
        )

class StockMovementDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = StockMovementSerializer
    
    def get_queryset(self):
        return StockMovement.objects.filter(company=self.request.user.company)

# ============================================
# PURCHASE ORDER VIEWS
# ============================================

class PurchaseOrderListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = PurchaseOrderSerializer
    
    def get_queryset(self):
        queryset = PurchaseOrder.objects.filter(company=self.request.user.company)
        branch = self.request.query_params.get('branch')
        status = self.request.query_params.get('status')
        supplier = self.request.query_params.get('supplier')
        
        if branch:
            queryset = queryset.filter(branch_id=branch)
        if status:
            queryset = queryset.filter(status=status)
        if supplier:
            queryset = queryset.filter(supplier_id=supplier)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(
            company=self.request.user.company,
            created_by=self.request.user
        )

class PurchaseOrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = PurchaseOrderSerializer
    
    def get_queryset(self):
        return PurchaseOrder.objects.filter(company=self.request.user.company)

class PurchaseOrderReceiveView(APIView):
    """Mark purchase order as received and update stock"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def post(self, request, pk):
        try:
            purchase_order = PurchaseOrder.objects.get(
                id=pk, 
                company=request.user.company
            )
            
            # Update status
            purchase_order.status = 'received'
            purchase_order.received_date = timezone.now().date()
            purchase_order.save()
            
            # Update stock for each item
            for item in purchase_order.items.all():
                if item.content_type and item.object_id:
                    product = item.content_type.get_object_for_this_type(id=item.object_id)
                    product.quantity_in_stock += item.quantity_ordered
                    product.save()
                    
                    # Create stock movement record
                    StockMovement.objects.create(
                        company=request.user.company,
                        branch=purchase_order.branch,
                        content_type=item.content_type,
                        object_id=item.object_id,
                        movement_type='purchase',
                        quantity=item.quantity_ordered,
                        previous_quantity=product.quantity_in_stock - item.quantity_ordered,
                        new_quantity=product.quantity_in_stock,
                        reference_id=purchase_order.order_number,
                        reference_model='PurchaseOrder',
                        notes=f'Received from PO #{purchase_order.order_number}',
                        performed_by=request.user
                    )
            
            serializer = PurchaseOrderSerializer(purchase_order)
            return Response(serializer.data)
            
        except PurchaseOrder.DoesNotExist:
            return Response(
                {'error': 'Purchase order not found'},
                status=status.HTTP_404_NOT_FOUND
            )

# ============================================
# WARRANTY VIEWS
# ============================================

class WarrantyListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = WarrantySerializer
    
    def get_queryset(self):
        queryset = Warranty.objects.filter(company=self.request.user.company)
        branch = self.request.query_params.get('branch')
        status = self.request.query_params.get('status')
        customer = self.request.query_params.get('customer')
        
        if branch:
            queryset = queryset.filter(branch_id=branch)
        if status:
            queryset = queryset.filter(status=status)
        if customer:
            queryset = queryset.filter(customer_id=customer)
        
        return queryset
    
    def perform_create(self, serializer):
        # Generate warranty number
        import uuid
        warranty_number = f"WAR-{uuid.uuid4().hex[:8].upper()}"
        serializer.save(
            company=self.request.user.company,
            warranty_number=warranty_number
        )

class WarrantyDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = WarrantySerializer
    
    def get_queryset(self):
        return Warranty.objects.filter(company=self.request.user.company)

# ============================================
# REPAIR VIEWS
# ============================================

class RepairListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = RepairSerializer
    
    def get_queryset(self):
        queryset = Repair.objects.filter(company=self.request.user.company)
        branch = self.request.query_params.get('branch')
        status = self.request.query_params.get('status')
        priority = self.request.query_params.get('priority')
        customer = self.request.query_params.get('customer')
        
        if branch:
            queryset = queryset.filter(branch_id=branch)
        if status:
            queryset = queryset.filter(status=status)
        if priority:
            queryset = queryset.filter(priority=priority)
        if customer:
            queryset = queryset.filter(customer_id=customer)
        
        return queryset
    
    def perform_create(self, serializer):
        # Generate repair number
        import uuid
        repair_number = f"REP-{uuid.uuid4().hex[:8].upper()}"
        serializer.save(
            company=self.request.user.company,
            created_by=self.request.user,
            repair_number=repair_number
        )

class RepairDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = RepairSerializer
    
    def get_queryset(self):
        return Repair.objects.filter(company=self.request.user.company)

class RepairCompleteView(APIView):
    """Mark repair as completed"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def post(self, request, pk):
        try:
            repair = Repair.objects.get(
                id=pk,
                company=request.user.company
            )
            
            repair.status = 'completed'
            repair.completed_date = timezone.now()
            repair.solution = request.data.get('solution', repair.solution)
            repair.actual_cost = request.data.get('actual_cost', repair.actual_cost)
            repair.save()
            
            serializer = RepairSerializer(repair)
            return Response(serializer.data)
            
        except Repair.DoesNotExist:
            return Response(
                {'error': 'Repair not found'},
                status=status.HTTP_404_NOT_FOUND
            )

# ============================================
# DASHBOARD VIEWS
# ============================================

class EPADashboardView(APIView):
    """EPA Shop Dashboard - Company specific"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get(self, request):
        company = request.user.company
        
        # Sales stats
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        total_sales = Sale.objects.filter(company=company).count()
        total_revenue = Sale.objects.filter(
            company=company,
            payment_status='paid'
        ).aggregate(total=Sum('net_amount'))['total'] or 0
        
        today_sales = Sale.objects.filter(
            company=company,
            sale_date__date=today
        ).count()
        
        today_revenue = Sale.objects.filter(
            company=company,
            sale_date__date=today,
            payment_status='paid'
        ).aggregate(total=Sum('net_amount'))['total'] or 0
        
        week_sales = Sale.objects.filter(
            company=company,
            sale_date__date__gte=week_ago
        ).count()
        
        month_revenue = Sale.objects.filter(
            company=company,
            sale_date__date__gte=month_ago,
            payment_status='paid'
        ).aggregate(total=Sum('net_amount'))['total'] or 0
        
        # Product counts
        electronics_count = Electronic.objects.filter(company=company, is_active=True).count()
        phones_count = Phone.objects.filter(company=company, is_active=True).count()
        accessories_count = Accessory.objects.filter(company=company, is_active=True).count()
        
        # Total stock value
        electronic_value = Electronic.objects.filter(company=company).aggregate(
            total=Sum(F('quantity_in_stock') * F('purchase_price'))
        )['total'] or 0
        
        phones_value = Phone.objects.filter(company=company).aggregate(
            total=Sum(F('quantity_in_stock') * F('purchase_price'))
        )['total'] or 0
        
        accessories_value = Accessory.objects.filter(company=company).aggregate(
            total=Sum(F('quantity_in_stock') * F('purchase_price'))
        )['total'] or 0
        
        total_stock_value = electronic_value + phones_value + accessories_value
        
        # Low stock items
        low_stock_electronics = Electronic.objects.filter(
            company=company,
            quantity_in_stock__lte=F('minimum_stock_level')
        ).count()
        
        low_stock_phones = Phone.objects.filter(
            company=company,
            quantity_in_stock__lte=F('minimum_stock_level')
        ).count()
        
        low_stock_accessories = Accessory.objects.filter(
            company=company,
            quantity_in_stock__lte=F('minimum_stock_level')
        ).count()
        
        # Recent sales
        recent_sales = Sale.objects.filter(
            company=company
        ).order_by('-sale_date')[:10]
        
        # Branch statistics
        branches = Branch.objects.filter(company=company, is_active=True)
        branch_stats = []
        for branch in branches:
            branch_sales = Sale.objects.filter(
                company=company,
                branch=branch,
                payment_status='paid'
            ).aggregate(total=Sum('net_amount'))['total'] or 0
            
            branch_stats.append({
                'id': branch.id,
                'name': branch.name,
                'code': branch.code,
                'total_sales': Sale.objects.filter(company=company, branch=branch).count(),
                'total_revenue': branch_sales
            })
        
        # Pending repairs
        pending_repairs = Repair.objects.filter(
            company=company,
            status__in=['pending', 'in_progress', 'waiting_parts']
        ).count()
        
        # Active warranties expiring soon (next 30 days)
        expiring_warranties = Warranty.objects.filter(
            company=company,
            status='active',
            end_date__lte=today + timedelta(days=30)
        ).count()
        
        return Response({
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'today_sales': today_sales,
            'today_revenue': today_revenue,
            'week_sales': week_sales,
            'month_revenue': month_revenue,
            'product_counts': {
                'electronics': electronics_count,
                'phones': phones_count,
                'accessories': accessories_count,
            },
            'stock_value': {
                'total': total_stock_value,
                'electronics': electronic_value,
                'phones': phones_value,
                'accessories': accessories_value,
            },
            'low_stock': {
                'electronics': low_stock_electronics,
                'phones': low_stock_phones,
                'accessories': low_stock_accessories,
            },
            'branches': branch_stats,
            'recent_sales': SaleSerializer(recent_sales, many=True).data,
            'pending_repairs': pending_repairs,
            'expiring_warranties': expiring_warranties,
            'timestamp': timezone.now()
        })