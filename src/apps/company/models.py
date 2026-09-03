from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.companies.models import Company
from apps.epa_shop.models import Branch

User = get_user_model()

class Expense(models.Model):
    """Expense tracking model for recording daily expenses"""
    
    # Payment Methods
    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('m-pesa', 'M-Pesa'),
        ('card', 'Card'),
        ('other', 'Other'),
    )
    
    # Expense Categories
    CATEGORY_RENT = 'rent'
    CATEGORY_SALARY = 'salary'
    CATEGORY_TRANSPORT = 'transport'
    CATEGORY_UTILITIES = 'utilities'
    CATEGORY_SUPPLIES = 'supplies'
    CATEGORY_MAINTENANCE = 'maintenance'
    CATEGORY_MARKETING = 'marketing'
    CATEGORY_TAX = 'tax'
    CATEGORY_INSURANCE = 'insurance'
    CATEGORY_OTHER = 'other'
    
    EXPENSE_CATEGORIES = (
        (CATEGORY_RENT, 'Rent'),
        (CATEGORY_SALARY, 'Salary'),
        (CATEGORY_TRANSPORT, 'Transport'),
        (CATEGORY_UTILITIES, 'Utilities'),
        (CATEGORY_SUPPLIES, 'Office Supplies'),
        (CATEGORY_MAINTENANCE, 'Maintenance'),
        (CATEGORY_MARKETING, 'Marketing'),
        (CATEGORY_TAX, 'Tax'),
        (CATEGORY_INSURANCE, 'Insurance'),
        (CATEGORY_OTHER, 'Other'),
    )
    
    # Status
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    
    EXPENSE_STATUS = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )
    
    # Basic Information
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='expenses'
    )
    branch = models.ForeignKey(
        Branch, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='expenses'
    )
    
    # Expense Details
    expense_date = models.DateField(default=timezone.now)
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORIES)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Payment Details
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    reference = models.CharField(max_length=100, blank=True, help_text="Invoice or receipt number")
    
    # Additional Info
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=EXPENSE_STATUS, default=STATUS_PENDING)
    
    # Audit Trail
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='expenses_created'
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='expenses_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'company_expenses'
        ordering = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'expense_date']),
            models.Index(fields=['company', 'category']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['expense_date']),
        ]
    
    def __str__(self):
        return f"{self.category} - {self.description} (KSh {self.amount})"
    
    @property
    def category_display(self):
        """Get the display name for the category"""
        for key, value in self.EXPENSE_CATEGORIES:
            if key == self.category:
                return value
        return self.category
    
    @property
    def status_display(self):
        """Get the display name for the status"""
        for key, value in self.EXPENSE_STATUS:
            if key == self.status:
                return value
        return self.status
    
    @property
    def payment_method_display(self):
        """Get the display name for the payment method"""
        for key, value in self.PAYMENT_METHODS:
            if key == self.payment_method:
                return value
        return self.payment_method
    
    def approve(self, user):
        """Approve the expense"""
        self.status = self.STATUS_APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()
    
    def reject(self):
        """Reject the expense"""
        self.status = self.STATUS_REJECTED
        self.save()