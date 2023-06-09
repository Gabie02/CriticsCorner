from django.contrib import messages
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import *
from .serializers import *


def index(request):
    movies = Movie.objects.all().order_by("-avg_rating")
    return render(request, 'review/list_movies.html', {'movies': movies})


def register_user(request):
    if request.method == "POST":
        username = request.POST.get('user')
        email = request.POST.get('email')
        password = request.POST.get('password')

        user = User.objects.create_user(username=username, email=email, password=password)
        rv = Reviewer(user=user)
        rv.save()
        watchlist = Watchlist(name="Default", reviewer_id=user.reviewer.id)
        watchlist.save()

        return HttpResponseRedirect(reverse('review:loginview'))
    else:
        return render(request, 'review/registeruser.html')


def loginview(request):
    if request.method == "POST":
        username = request.POST.get('user')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse('review:index'))
        else:
            return render(request, 'review/login.html', {'error_message': "Invalid username or password!"}, )
    else:
        return render(request, 'review/login.html')


@login_required(login_url='review:loginview')
def upload_picture(request):
    watchlists = Watchlist.objects.filter(reviewer_id=request.user.reviewer.id)
    movies_in_watchlists = []
    for watchlist in watchlists:
        movies = watchlist.movies.all()
        movies_in_watchlists.append((watchlist, movies))

    context = {
        'movies_in_watchlists': movies_in_watchlists
    }

    if request.method == 'POST' and request.FILES['myfile']:
        myfile = request.FILES['myfile']

        fs = FileSystemStorage()
        filename = fs.save(myfile.name, myfile)
        uploaded_file_url = fs.url(filename)
        uploaded_file_url = uploaded_file_url.replace("/review/static", "")
        request.user.reviewer.profile_picture = uploaded_file_url
        request.user.reviewer.save()

        try:
            watchlists = Watchlist.objects.filter(reviewer=request.user.reviewer.id)
        except Watchlist.DoesNotExist:
            watchlists = None

        context = {
            'uploaded_file_url': uploaded_file_url,
            'movies_in_watchlists': movies_in_watchlists
        }

        return render(request, 'review/watchlist.html', context)

    return render(request, 'review/watchlist.html', context)


@login_required(login_url='review:loginview')
def logoutview(request):
    logout(request)
    return HttpResponseRedirect(reverse('review:index'))


@login_required(login_url='review:loginview')
def details(request, movie_id):
    movie = get_object_or_404(Movie, pk=movie_id)
    reviews = Review.objects.select_related('reviewer').all() \
        .filter(movie=movie) \
        .exclude(comment=None) \
        .order_by("-is_critic_approved", "-likes_count")
    ratings_list = []
    for r in reviews:
        print(r.reviewer)
        ratings_list.append(r.rating)
    calculate_rating(movie, ratings_list)
    try:
        watchlists = Watchlist.objects.filter(reviewer=request.user.reviewer.id)
    except Watchlist.DoesNotExist:
        watchlists = None

    context = {
        'movie': movie,
        'reviews': reviews,
        'watchlists': watchlists
    }
    return render(request, 'review/details.html', context)


@login_required(login_url='review:loginview')
def review_movie(request, movie_id):
    # # Ver se o objeto movie tem acesso a todas as reviews
    movie = get_object_or_404(Movie, pk=movie_id)

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('review:details', args=(movie_id,)))

    try:
        rating = request.POST['rating']  # Rating é obrigatório para todas as reviews
        comment = request.POST['comment']
    except KeyError:
        messages.error(request=request, message="Fields missing")
        return HttpResponseRedirect(reverse('review:details', args=(movie_id,)))

    already_reviewed = Review.objects.filter(movie=movie, reviewer=request.user.reviewer).count()
    if not already_reviewed:
        if rating:
            if not comment or comment == "":
                comment = None  # <-- Ver se isto é transformado para 'null' na base de dados

            new_review = Review(rating=rating,
                                comment=comment,
                                likes_count=0,
                                created_at=timezone.now(),
                                movie_id=movie_id,
                                reviewer_id=request.user.reviewer.id)
            new_review.save()

            messages.success(request=request, message="Review successfully added!")
            return HttpResponseRedirect(reverse('review:details', args=(movie_id,)))

        messages.error(request=request, message="Review does not have a rating.")
        return HttpResponseRedirect(reverse('review:details', args=(movie_id,)))

    messages.error(request=request, message="You already reviewed this movie.")
    return HttpResponseRedirect(reverse('review:details', args=(movie_id,)))


@permission_required('auth.delete_review')
def delete_review(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    review.delete()
    return HttpResponseRedirect(reverse('review:details', args=(review.movie.id,)))


@permission_required('auth.delete_movie')
def delete_movie(request, movie_id):
    movie = get_object_or_404(Movie, pk=movie_id)
    movie.delete()
    return HttpResponseRedirect(reverse('review:index'))


@login_required(login_url='review:loginview')
def create_watchlist(request):
    if request.method == 'POST':
        watchlist_name = request.POST.get('name')
        reviewer = request.user.reviewer.id
        watchlist = Watchlist(name=watchlist_name, reviewer_id=reviewer)
        watchlist.save()
        messages.success(request=request, message="Watchlist successfully added!")
        return HttpResponseRedirect(reverse('review:display_watchlist'))
    else:
        return render(request, 'review/watchlist.html')


@login_required(login_url='review:loginview')
def delete_watchlist(request, watchlist_id):
    watchlist = get_object_or_404(Watchlist, pk=watchlist_id)
    watchlist.delete()
    messages.success(request=request, message="Watchlist successfully deleted!")
    return HttpResponseRedirect(reverse('review:display_watchlist'))


@login_required(login_url='review:loginview')
def add_to_watchlist(request, movie_id):
    if request.method == 'POST':
        watchlist_id = request.POST.get('watchlist_id')
        watchlist = get_object_or_404(Watchlist, pk=watchlist_id)
        movie = Movie.objects.get(pk=movie_id)

        if watchlist.movies.filter(pk=movie_id).exists():
            messages.warning(request, 'Movie is already in the watchlist!')
            return HttpResponseRedirect(reverse('review:details', args=(movie.id,)))
        else:
            watchlist.movies.add(movie)
            messages.success(request, 'Movie successfully added!')
        return HttpResponseRedirect(reverse('review:details', args=(movie.id,)))
    else:
        return render(request, 'review/details.html')


@login_required(login_url='review:loginview')
def delete_from_watchlist(request, movie_id, watchlist_id):
    if request.method == 'POST':
        watchlist_id = request.POST.get('watchlist_id')
        watchlist = get_object_or_404(Watchlist, pk=watchlist_id)
        movie = Movie.objects.get(pk=movie_id)

        if watchlist.movies.filter(pk=movie_id).exists():
            watchlist.movies.remove(movie)
            messages.success(request, 'Movie deleted from the watchlist.')
            return HttpResponseRedirect(reverse('review:display_watchlist'))
        else:
            messages.error(request, 'Couldn´t delete movie from watchlist!')
            return render(request, 'review/watchlist.html')
    return render(request, 'review/watchlist.html')


@login_required(login_url='review:loginview')
def display_watchlist(request):
    watchlists = Watchlist.objects.filter(reviewer_id=request.user.reviewer.id)
    movies_in_watchlists = []
    for watchlist in watchlists:
        movies = watchlist.movies.all()
        movies_in_watchlists.append((watchlist, movies))
    return render(request, 'review/watchlist.html', {'movies_in_watchlists': movies_in_watchlists})


@login_required(login_url='review:loginview')
def like_movie(request, review_id):
    review = Review.objects.get(pk=review_id)
    reviewer_liking = request.user.reviewer
    current_likes = review.likes_count

    liked = Like.objects.filter(reviewer=reviewer_liking, review=review).count()

    if not liked:
        like = Like.objects.create(reviewer=reviewer_liking, review=review, created_at=timezone.now())
        current_likes = current_likes + 1
    review.likes_count = current_likes
    review.save()
    return HttpResponseRedirect(reverse('review:review_movie', args=(review.movie.id,)))


def approve_review(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    if not review.is_critic_approved:
        review.is_critic_approved = True
        review.save()

    messages.success(request, "Review approved successfully")
    return HttpResponseRedirect(reverse('review:review_movie', args=(review.movie_id,)))


def calculate_rating(movie, ratings_list):
    if len(ratings_list) > 0:
        average = sum(ratings_list) / len(ratings_list)
        movie.avg_rating = average
        movie.save()
    else:
        movie.avg_rating = None
        movie.save()


@api_view(['GET'])
def list_movies(request):
    movies = Movie.objects.prefetch_related('reviews_received').filter(reviews_received__isnull=False).distinct()
    movie_serializer = MovieSerializer(movies, context={'request': request}, many=True)
    return Response(movie_serializer.data)


# @api_view(['GET'])
# def movie_detail(request, movie_id):
#     try:
#         movie = Movie.objects.get(pk=movie_id)
#     except Movie.DoesNotExist:
#         return Response(status=status.HTTP_404_NOT_FOUND)
def send_to_front_end(request):
    return HttpResponseRedirect('http://localhost:3000/')  # Redireciona ao react
