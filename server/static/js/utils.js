// A seat map puts each seat's tooltip in a hidden .seat-tooltip right after the seat,
// or after the link around it.
function seatTooltip(seat) {
  var next = (seat.parentElement && seat.parentElement.tagName === 'A' ? seat.parentElement : seat).nextElementSibling;
  return next && next.classList.contains('seat-tooltip') ? next : null;
}

// One delegated Bootstrap tooltip covers every page: seats show their .seat-tooltip,
// and anything else marked data-bs-toggle="tooltip" shows its data-bs-title.
document.addEventListener('DOMContentLoaded', function () {
  if (!window.bootstrap) {
    return;
  }
  new bootstrap.Tooltip(document.body, {
    selector: '[data-bs-toggle="tooltip"], .s, .layout-seat',
    html: true,
    // keep the photos' data-photo, which the sanitizer would strip
    allowList: Object.assign({}, bootstrap.Tooltip.Default.allowList, {
      img: bootstrap.Tooltip.Default.allowList.img.concat(['data-photo']),
    }),
    title: function (element) {
      var tooltip = seatTooltip(element);
      // this function overrides data-bs-title, so read it here
      return tooltip ? tooltip.innerHTML : element.getAttribute('data-bs-title');
    },
  });
});

// Photos show the placeholder first, since fetching one can take a while (the course's Canvas roster
// and Cal1Card are asked), and are swapped in once loaded. No photo is an empty 204, which fails to load
// as an image: the placeholder stays.
var photoLoaded = {};  // by url: true once loaded, false if there's none, null while loading

function showPhotos(images) {
  images.forEach(function (img) {
    var url = img.getAttribute('data-photo');
    if (photoLoaded[url]) {
      img.src = url;
    } else if (!(url in photoLoaded)) {
      photoLoaded[url] = null;
      var photo = new Image();
      photo.onload = function () {
        photoLoaded[url] = true;
        // every copy, including a seat's hidden tooltip, so the next one shown has the photo
        document.querySelectorAll('img.photo[data-photo]').forEach(function (other) {
          if (other.getAttribute('data-photo') === url) {
            other.src = url;
          }
        });
      };
      photo.onerror = function () {
        photoLoaded[url] = false;
      };
      photo.src = url;
    }
  });
}

document.addEventListener('DOMContentLoaded', function () {
  // not the seats' hidden tooltips: only fetch a seat's photo when its tooltip is shown
  showPhotos(Array.prototype.filter.call(document.querySelectorAll('img.photo[data-photo]'), function (img) {
    return !img.closest('.seat-tooltip');
  }));
});

document.addEventListener('inserted.bs.tooltip', function () {
  showPhotos(document.querySelectorAll('.tooltip img.photo[data-photo]'));
});
