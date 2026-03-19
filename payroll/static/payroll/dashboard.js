staticUrl = $("#statiUrl").attr("data-url");

$(document).ready(function () {
  var myDate = new Date();
  var year = myDate.getFullYear();
  var month = ("0" + myDate.getMonth()).slice(-2);
  if (month == "00") {
    month = "12";
    year = year - 1;
  }
  var formattedDate = year + "-" + month;
  var start_index = 0;
  var per_page = 10;
  var initialLoad = true;

  $("#monthYearField").val(formattedDate);

  function isChartEmpty(chartData) {
    if (!chartData) {
      return true;
    }
    for (let i = 0; i < chartData.length; i++) {
      const hasNonZeroValues = chartData[i].data.some((value) => value !== 0);
      if (hasNonZeroValues) {
        return false; // Return false if any non-zero value is found
      }
    }
    return true; // Return true if all values are zero
  }



  function payslip_details() {
    var period = $("#monthYearField").val();
    $.ajax({
      url: "/payroll/dashboard-payslip-details",
      type: "GET",
      dataType: "json",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
      data: {
        period: period,
      },
      success: (response) => {
        $(".payslip-number").html(response.no_of_emp);
        $(".payslip-amount").html(response.total_amount);
      },
      error: (error) => {
        console.log("Error", error);
      },
    });
  }

  // ===== DRILL-DOWN 3 LIVELLI: area → store → dipendenti =====
  // level: 'area' | 'store' | 'employees'
  // param: store_name (solo per level='employees')
  function department_chart_view(level, param) {
    level = level || "area";
    var period = $("#monthYearField").val();

    var url, requestData;
    if (level === "area") {
      url = "/payroll/dashboard-department-chart";
      requestData = { period: period };
    } else if (level === "store") {
      url = "/payroll/dashboard-store-drilldown";
      requestData = { period: period };
    } else {
      url = "/payroll/dashboard-store-employees";
      requestData = { period: period, store_name: param };
    }

    // Titoli e label lista in base al livello
    var chartTitle =
      level === "area"
        ? "Work Area Chart"
        : level === "store"
        ? "Negozi"
        : "Dipendenti – " + param;
    var listTitle =
      level === "area"
        ? "Totale per Area"
        : level === "store"
        ? "Totale per Negozio"
        : "Netto per Dipendente";

    function buildBackButtons() {
      var html = "";
      if (level === "store") {
        html =
          '<button id="dept_back_l1" class="oh-btn oh-btn--secondary oh-btn--shadow mb-2 me-2"><ion-icon name="arrow-back-outline"></ion-icon> Aree</button>';
      } else if (level === "employees") {
        html =
          '<button id="dept_back_l1" class="oh-btn oh-btn--secondary oh-btn--shadow mb-2 me-2"><ion-icon name="arrow-back-outline"></ion-icon> Aree</button>' +
          '<button id="dept_back_l2" class="oh-btn oh-btn--secondary oh-btn--shadow mb-2"><ion-icon name="arrow-back-outline"></ion-icon> Negozi</button>';
      }
      return html;
    }

    function renderChart(dataSet, labels) {
      $("#department_canvas_body").html(
        buildBackButtons() + '<canvas id="departmentChart"></canvas>'
      );
      $("#dept_chart_title").text(chartTitle);
      $("#area_list_title").text(listTitle);

      $("#dept_back_l1").on("click", function () {
        department_chart_view("area");
      });
      $("#dept_back_l2").on("click", function () {
        department_chart_view("store");
      });

      var chartType = level === "employees" ? "bar" : "pie";

      var chartConfig = {
        type: chartType,
        data: {
          labels: labels,
          datasets: dataSet.map(function (ds) {
            return Object.assign({}, ds, { borderWidth: 0 });
          }),
        },
        options: {
          onClick: function (event, elements) {
            if (!elements.length) return;
            var idx = elements[0].index;
            var clicked = labels[idx];

            if (level === "area" && clicked === "NEGOZI") {
              department_chart_view("store");
            } else if (level === "store") {
              department_chart_view("employees", clicked);
            }
          },
          plugins: {
            tooltip: {
              callbacks: {
                label: function (context) {
                  var val = context.parsed;
                  if (chartType === "pie") val = context.parsed;
                  else val = context.parsed.y;
                  return " € " + val.toFixed(2);
                },
                title: function (context) {
                  return context[0].label;
                },
              },
            },
            legend: { display: chartType === "pie" },
          },
          scales:
            chartType === "bar"
              ? {
                  x: { ticks: { maxRotation: 45, minRotation: 30 } },
                  y: {
                    title: { display: true, text: "€" },
                    ticks: {
                      callback: function (v) {
                        return "€ " + v;
                      },
                    },
                  },
                }
              : {},
        },
      };

      var chart = new Chart(
        document.getElementById("departmentChart"),
        chartConfig
      );

      // Rimosso il vecchio listener jQuery on("click") — ora gestito da onClick in chartConfig
    }

    $.ajax({
      url: url,
      type: "GET",
      dataType: "json",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      data: requestData,
      success: function (response) {
        var dataSet = response.dataset;
        var labels = response.labels;
        var totals = response.department_total || [];

        // Aggiorna lista laterale
        if (totals.length) {
          $("#department_total").show().html("");
          $("#department_total_empty").hide();
          $.each(totals, function (i, v) {
            $("#department_total").append(
              "<li class='m-3' style='cursor:default'><span>" +
                v.department +
                "</span>: <b>€ " +
                parseFloat(v.amount).toFixed(2) +
                "</b></li>"
            );
          });
        } else {
          // per level=employees costruiamo la lista dai dataset
          if (dataSet.length && dataSet[0].data.length) {
            $("#department_total").show().html("");
            $("#department_total_empty").hide();
            $.each(labels, function (i, name) {
              $("#department_total").append(
                "<li class='m-3' style='cursor:default'><span>" +
                  name +
                  "</span>: <b>€ " +
                  parseFloat(dataSet[0].data[i]).toFixed(2) +
                  "</b></li>"
              );
            });
          } else {
            $("#department_total").hide();
            $("#department_total_empty").show().html(
              '<div style="display:flex;align-items:center;justify-content:center;padding-top:50px">' +
                '<div><img style="display:block;width:70px;margin:10px auto" src="' +
                staticUrl +
                'images/ui/money.png" />' +
                '<h3 style="font-size:16px" class="oh-404__subtitle">' +
                response.message +
                "</h3></div></div>"
            );
          }
        }

        if (isChartEmpty(dataSet)) {
          $("#department_canvas_body").html(
            '<div style="height:310px;display:flex;align-items:center;justify-content:center">' +
              '<div><img style="display:block;width:70px;margin:10px auto" src="' +
              staticUrl +
              'images/ui/no-money.png" />' +
              '<h3 style="font-size:16px" class="oh-404__subtitle">' +
              response.message +
              "</h3></div></div>"
          );
          $("#dept_chart_title").text(chartTitle);
          $("#area_list_title").text(listTitle);
        } else {
          renderChart(dataSet, labels);
        }
      },
      error: function (err) {
        console.log("Error", err);
      },
    });
  }

  function contract_ending(initialLoad) {
    var period = $("#monthYearField").val();
    var date = period.split("-");
    var year = date[0];
    var month = parseInt(date[1]);

    var monthNames = [
      "January",
      "February",
      "March",
      "April",
      "May",
      "June",
      "July",
      "August",
      "September",
      "October",
      "November",
      "December",
    ];
    if (initialLoad) {
      let date = new Date();
      let year = date.getFullYear();
      let month = date.getMonth();
      var formattedDate = `${monthNames[month]} ${year}`;
    } else {
      var formattedDate = `${monthNames[month - 1]} ${year}`;
    }

    $.ajax({
      url: "/payroll/dashboard-contract-ending",
      type: "GET",
      dataType: "json",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
      data: {
        period: period,
        initialLoad: initialLoad,
      },
      success: (response) => {
        var contract_end = response.contract_end;
        if (contract_end.length != 0) {
          $("#contract_ending").html("");
          $.each(contract_end, function (key, value) {
            id = value.contract_id;
            elem = `<li class='m-3 contract_id' style = "cursor: pointer;" data-id=${id}> ${value.contract_name} </li>`;

            $("#contract_ending").append(elem);
          });
          $(".contract-number").html(
            `${formattedDate} : ${contract_end.length}`
          );
        } else {
          $(".contract-number").html(
            `${formattedDate} : ${contract_end.length}`
          );
          $("#contract_ending").html(
            `<div style="display:flex;align-items: center;justify-content: center; padding-top:50px" class="">
              <div style="" class="">
                <img style="display: block;width: 70px;margin: 10px auto ;" src="${
                  staticUrl + "images/ui/contract.png"
                }" class="" alt=""/>
                <h3 style="font-size:16px" class="oh-404__subtitle">${
                  response.message
                }</h3>
              </div>
            </div>`
          );
        }
      },
      error: (error) => {
        console.log("Error", error);
      },
    });
  }

  payslip_details();
  department_chart_view("area");
  contract_ending(initialLoad);

  $("#monthYearField").on("change", function () {
    initialLoad = false;
    payslip_details();
    department_chart_view("area");
    contract_ending(initialLoad);
  });

  $(".filter").on("click", function () {
    $("#back_button").removeClass("d-none");
  });

  $("#contract_ending").on("click", ".contract_id", function () {
    id = $(this).data("id");
    $.ajax({
      url: "/payroll/single-contract-view/" + id,
      type: "GET",
      dataType: "html",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
      data: {
        dashboard: "dashboard",
      },
      success: (response) => {
        $("#ContractModal").toggleClass("oh-modal--show");
        $("#contract_target").html(response);
      },
      error: (error) => {
        console.log("Error", error);
      },
    });
  });

  $("#ContractModal").on("click", ".oh-modal__close", function () {
    $("#ContractModal").removeClass("oh-modal--show");
  });
});
