(function () {
    'use strict';

    /*jslint
        browser: true
    */
    /*global
        L, reqwest
    */

    var map;

    function arrowMarker(location) {
        var direction = (location.direction || 0) - 135;
        var tooltip = location.datetime.toTimeString().slice(0, 8);
        tooltip += getTooltip(location.delta);

        return L.marker(location.coordinates, {
            icon: L.divIcon({
                iconSize: [16, 16],
                html: '<div class="arrow" style="-webkit-transform: rotate(' + direction + 'deg);transform: rotate(' + direction + 'deg)"></div>',
                className: 'just-arrow',
            })
        }).bindTooltip(tooltip);

    }

    var circleMarkerOptions = {
        radius: 2,
        fillColor: '#000',
        fillOpacity: 1,
        weight: 0,
    };

    var date = document.getElementById('date').value;

    function closeMap() {
        if (lastRequest) {
            lastRequest.abort();
        }
        window.location.hash = ''; // triggers hashchange event
    }

    window.onkeydown = function(event) {
        if (event.keyCode === 27) { // esc
            closeMap();
        }
    };

    var lastRequest;

    window.onhashchange = maybeOpenMap;

    function getTooltip(delta) {
        if (delta) {
            var tooltip = 'About ';
            if (delta > 0) {
                tooltip += delta;
            } else {
                tooltip += delta * -1;
            }
            tooltip += ' minute';
            if (delta !== 1 && delta !== -1) {
                tooltip += 's';
            }
            if (delta > 0) {
                tooltip += ' early';
            } else {
                tooltip += ' late';
            }
            return '<br>' + tooltip;
        } else if (delta === 0) {
            return '<br>On time';
        } else {
            return '';
        }
    }

    function maybeOpenMap() {
        var journey = window.location.hash.slice(1);

        if (journey) {
            var element = document.getElementById(journey);
        }

        if (!element) {
            return;
        }

        if (lastRequest) {
            lastRequest.abort();
        }

        if (map) {
            map.remove();
            map = null;
        }

        reqwest('/' + journey + '.json', function(response) {
            var i, actual;

            for (i = 0; i < response.locations.length; i++) {
                var location = response.locations[i];
                location.coordinates = L.latLng(location.coordinates[1], location.coordinates[0]);
                location.datetime = new Date(location.datetime);
            }

            if (response.stops) {
                var tripElement = document.createElement('div');
                tripElement.className = 'trip';
                element.appendChild(tripElement);

                var table = document.createElement('table');
                table.className = 'trip-timetable';
                var thead = document.createElement('thead');
                thead.innerHTML = '<tr><th scope="col">Stop</th><th scope="col">Timetable</th><th>Actual</th></tr>';
                table.appendChild(thead);

                var tbody = document.createElement('tbody');
                var tr, stop, time;
                for (i = 0; i < response.stops.length; i++) {
                    tr = document.createElement('tr');
                    stop = response.stops[i];
                    if (stop.minor) {
                        tr.className = 'minor';
                    }
                    time = stop.aimed_departure_time || stop.aimed_arrival_time || '';
                    time += '</td><td>';
                    if (stop.actual_departure_time) {
                        actual = new Date(stop.actual_departure_time);
                        time += actual.toTimeString().slice(0, 5);
                    }
                    tr.innerHTML = '<td>' + stop.name + '</th><td>' + time + '</td>';
                    tbody.appendChild(tr);

                    if (stop.coordinates) {
                        stop.coordinates = L.GeoJSON.coordsToLatLng(stop.coordinates);
                    }
                    stop.tr = tr;
                }
                table.appendChild(tbody);
                tripElement.appendChild(table);
            }

            var mapContainer = element.querySelector('.map');
            if (!mapContainer) {
                mapContainer = document.createElement('div');
                mapContainer.className = 'map';
                element.appendChild(mapContainer);
            }

            map = L.map(mapContainer, {
                tap: false
            });
            window.bustimes.doTileLayer(map);

            L.control.locate().addTo(map);

            if (response.stops) {
                var html = '<div class="stop-arrow no-direction"></div>';
                var openTooltip;
                response.stops.forEach(function(stop) {
                    if (stop.coordinates) {
                        var marker = L.marker(stop.coordinates, {
                            icon: L.divIcon({
                                iconSize: [9, 9],
                                html: html,
                                className: 'stop'
                            })
                        }).bindTooltip(stop.name);

                        marker.addTo(map);

                        var showStop = function() {
                            if (openTooltip) {
                                openTooltip.closeTooltip();
                            }
                            openTooltip = marker.openTooltip();
                        };

                        stop.tr.addEventListener('mouseover', showStop, {
                            passive: true
                        });
                        stop.tr.addEventListener('touchstart', showStop, {
                            passive: true
                        });
                    }
                });
            }

            var line = [],
                previousCoordinates,
                previousTimestamp,
                previousMarkerCoordinates,
                previousSkippedLocation;

            response.locations.forEach(function(location) {
                var timestamp = location.datetime.getTime();

                var coordinates = location.coordinates;

                line.push(coordinates);

                if (previousCoordinates) {
                    var time = timestamp - previousTimestamp;

                    if (previousMarkerCoordinates.distanceTo(location.coordinates) > 100) {
                        // vehicle has moved far enough
                        if (previousSkippedLocation) {
                            // mark the end of the stationary period
                            arrowMarker(previousSkippedLocation).addTo(map);
                            previousSkippedLocation = null;
                        }
                        arrowMarker(location).addTo(map);
                        previousMarkerCoordinates = location.coordinates;
                    } else {
                        // vehicle has barely moved
                        previousSkippedLocation = location;
                    }

                    // add a marker every minute
                    if (time && time < 6000000) {  // less than 10 minutes
                        var latDistance = coordinates.lat - previousCoordinates.lat;
                        var lngDistance = coordinates.lng - previousCoordinates.lng;
                        var latSpeed = latDistance / time;  // really velocity
                        var lngSpeed = lngDistance / time;

                        var minute = Math.ceil(previousTimestamp / 60000) * 60000 - previousTimestamp;
                        for (; minute <= time; minute += 60000) {
                            L.circleMarker(L.latLng(
                                previousCoordinates.lat + latSpeed * minute,
                                previousCoordinates.lng + lngSpeed * minute
                            ), circleMarkerOptions).addTo(map);
                        }
                    }
                } else {
                    arrowMarker(location).addTo(map);
                    previousMarkerCoordinates = location.coordinates;
                }

                previousCoordinates = coordinates;
                previousTimestamp = timestamp;
            });
            if (previousSkippedLocation) { 
                arrowMarker(previousSkippedLocation).addTo(map);
            }

            line = L.polyline(line, {
                weight: 4,
                color: '#87f',
                opacity: .5
            });
            line.addTo(map);

            var bounds = line.getBounds();

            map.fitBounds(bounds, {
                maxZoom: 14
            }).setMaxBounds(bounds.pad(.5));
        });
    }

    window.addEventListener('load', maybeOpenMap);

    function handleClick(event) {
        window.history.replaceState(null, null, '?date=' + date + event.target.hash);
        maybeOpenMap();

        var canonical = document.querySelector('link[rel="canonical"]');
        if (canonical) {
            canonical.remove();
        }
    }

    var links = document.querySelectorAll('a[href^="#journeys/"]');
    for (var i = links.length - 1; i >= 0; i -= 1) {
        links[i].addEventListener('click', handleClick);
    }

})();
