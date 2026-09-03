from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from datetime import timedelta

from .models import (
    Category, Supplier, Product, PriceHistory, Inventory,
    PurchaseOrder, PurchaseOrderItem, Sale, SaleItem,
    Customer, Discount, ShelfLocation
)
from .serializers import (
    CategorySerializer, SupplierSerializer, ProductSerializer,
    InventorySerializer, PurchaseOrderSerializer, PurchaseOrderItemSerializer,
    SaleSerializer, SaleItemSerializer, CustomerSerializer,
    DiscountSerializer, ShelfLocationSerializer
)
from apps.accounts.permissions import IsCompanyAdmin

# ============================================
# CATEGORY VIEWS
# ============================================

class CategoryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        return Category.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        return Category.objects.filter(company=self.request.user.company)

# ============================================
# SUPPLIER VIEWS
# ============================================

class SupplierListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = SupplierSerializer
    
    def get_queryset(self):
        return Supplier.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = SupplierSerializer
    
    def get_queryset(self):
        return Supplier.objects.filter(company=self.request.user.company)

# ============================================
# PRODUCT VIEWS
# ============================================

class ProductListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = ProductSerializer
    
    def get_queryset(self):
        return Product.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = ProductSerializer
    
    def get_queryset(self):
        return Product.objects.filter(company=self.request.user.company)

# ============================================
# INVENTORY VIEWS
# ============================================

class InventoryListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = InventorySerializer
    
    def get_queryset(self):
        return Inventory.objects.filter(company=self.request.user.company)

class LowStockView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get(self, request):
        company = request.user.company
        low_stock_products = Product.objects.filter(
            company=company,
            quantity_in_stock__lte=F('minimum_stock_level')
        )
        serializer = ProductSerializer(low_stock_products, many=True)
        return Response({
            'count': low_stock_products.count(),
            'products': serializer.data
        })

# ============================================
# PURCHASE ORDER VIEWS
# ============================================

class PurchaseOrderListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = PurchaseOrderSerializer
    
    def get_queryset(self):
        return PurchaseOrder.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, created_by=self.request.user)

class PurchaseOrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = PurchaseOrderSerializer
    
    def get_queryset(self):
        return PurchaseOrder.objects.filter(company=self.request.user.company)

# ============================================
# SALE VIEWS
# ============================================

class SaleListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = SaleSerializer
    
    def get_queryset(self):
        return Sale.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, sold_by=self.request.user)

class SaleDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = SaleSerializer
    
    def get_queryset(self):
        return Sale.objects.filter(company=self.request.user.company)

# ============================================
# CUSTOMER VIEWS
# ============================================

class CustomerListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = CustomerSerializer
    
    def get_queryset(self):
        return Customer.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = CustomerSerializer
    
    def get_queryset(self):
        return Customer.objects.filter(company=self.request.user.company)

# ============================================
# DISCOUNT VIEWS
# ============================================

class DiscountListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = DiscountSerializer
    
    def get_queryset(self):
        return Discount.objects.filter(company=self.request.user.company)
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

class DiscountDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    serializer_class = DiscountSerializer
    
    def get_queryset(self):
        return Discount.objects.filter(company=self.request.user.company)

# ============================================
# DASHBOARD VIEW
# ============================================

class SupermarketDashboardView(APIView):
    """Supermarket Dashboard - Company specific"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get(self, request):
        company = request.user.company
        
        # Today's date
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Sales stats
        total_sales = Sale.objects.filter(company=company).count()
        total_revenue = Sale.objects.filter(company=company).aggregate(
            total=Sum('total_amount')
        )['total'] or 0
        
        today_sales = Sale.objects.filter(
            company=company,
            sale_date__date=today
        ).count()
        
        today_revenue = Sale.objects.filter(
            company=company,
            sale_date__date=today
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Product counts
        total_products = Product.objects.filter(company=company).count()
        low_stock = Product.objects.filter(
            company=company,
            quantity_in_stock__lte=F('minimum_stock_level')
        ).count()
        
        # Suppliers
        total_suppliers = Supplier.objects.filter(company=company).count()
        
        # Customers
        total_customers = Customer.objects.filter(company=company).count()
        
        # Recent sales
        recent_sales = Sale.objects.filter(
            company=company
        ).order_by('-sale_date')[:5]
        
        return Response({
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'today_sales': today_sales,
            'today_revenue': today_revenue,
            'total_products': total_products,
            'low_stock_items': low_stock,
            'total_suppliers': total_suppliers,
            'total_customers': total_customers,
            'recent_sales': SaleSerializer(recent_sales, many=True).data,
            'timestamp': timezone.now()
        })
