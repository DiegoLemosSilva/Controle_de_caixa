from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.businesses.mixins import BusinessRequiredMixin

from .forms import ProductForm
from .models import Product


class ProductListView(BusinessRequiredMixin, ListView):
    template_name = 'products/product_list.html'
    context_object_name = 'products'
    paginate_by = 50

    def get_queryset(self):
        queryset = Product.objects.filter(business=self.business).order_by('name')
        query = self.request.GET.get('q', '').strip()
        return queryset.filter(name__icontains=query) if query else queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '').strip()
        return context


class ProductCreateView(BusinessRequiredMixin, CreateView):
    template_name = 'products/product_form.html'
    form_class = ProductForm
    success_url = reverse_lazy('products:product_list')

    def form_valid(self, form):
        form.instance.business = self.business
        messages.success(self.request, 'Produto cadastrado com sucesso.')
        return super().form_valid(form)


class ProductUpdateView(BusinessRequiredMixin, UpdateView):
    template_name = 'products/product_form.html'
    form_class = ProductForm
    success_url = reverse_lazy('products:product_list')

    def get_queryset(self):
        return Product.objects.filter(business=self.business)

    def form_valid(self, form):
        messages.success(self.request, 'Produto atualizado com sucesso.')
        return super().form_valid(form)


class ProductToggleActiveView(BusinessRequiredMixin, View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, business=self.business)
        product.is_active = not product.is_active
        product.save(update_fields=['is_active'])
        if product.is_active:
            messages.success(request, f'Produto "{product.name}" ativado com sucesso.')
        else:
            messages.success(request, f'Produto "{product.name}" inativado com sucesso.')
        return redirect('products:product_list')


class ProductDeleteView(BusinessRequiredMixin, View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, business=self.business)
        name = product.name
        product.delete()
        messages.success(request, f'Produto "{name}" excluído com sucesso.')
        return redirect('products:product_list')
